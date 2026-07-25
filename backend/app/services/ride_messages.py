"""Data access for per-ride messages, on two separate channels.

``client`` is the passenger<->driver thread. ``internal`` is staff-only: the ride
owner and the driver the ride was handed to (see ``services/assignment.py``) — the
passenger must never see it, so EVERY query here is channel-scoped and the
passenger-facing helpers hard-code ``client``.

Thin query helpers over ``RideMessage``; the ride's tenant and the viewer's
identity are resolved and authorized by the API layer. Unread is always a live
COUNT of the other party's still-unread messages — opening a thread stamps
``read_at`` on them, so there is no counter to desync. On the internal channel both
sides are staff, so "the other party" is by TENANT, not by sender.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ride, RideMessage, RideMessageChannel, RideMessageSender

logger = logging.getLogger("blackvolt.ride_messages")


def other_side(side: RideMessageSender) -> RideMessageSender:
    return (
        RideMessageSender.driver
        if side == RideMessageSender.client
        else RideMessageSender.client
    )


async def list_messages(
    db: AsyncSession,
    *,
    ride_id: int,
    after_id: int | None = None,
    limit: int = 200,
    channel: RideMessageChannel = RideMessageChannel.client,
) -> list[RideMessage]:
    q = select(RideMessage).where(
        RideMessage.ride_id == ride_id, RideMessage.channel == channel
    )
    if after_id is not None:
        q = q.where(RideMessage.id > after_id)
    q = q.order_by(RideMessage.id.asc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def add_message(
    db: AsyncSession,
    *,
    tenant_id: int,
    ride_id: int,
    sender: RideMessageSender,
    body: str,
    channel: RideMessageChannel = RideMessageChannel.client,
) -> RideMessage:
    msg = RideMessage(
        tenant_id=tenant_id,
        ride_id=ride_id,
        sender=sender,
        body=body,
        channel=channel,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def mark_read(
    db: AsyncSession,
    *,
    ride_id: int,
    reader_side: RideMessageSender,
    now: dt.datetime | None = None,
    channel: RideMessageChannel = RideMessageChannel.client,
) -> int:
    """Stamp ``read_at`` on the messages written by the OTHER party. Returns how
    many were newly marked (0 when the reader was already caught up)."""
    res = await db.execute(
        update(RideMessage)
        .where(
            RideMessage.ride_id == ride_id,
            RideMessage.channel == channel,
            RideMessage.sender == other_side(reader_side),
            RideMessage.read_at.is_(None),
        )
        .values(read_at=now or dt.datetime.now(dt.UTC))
    )
    await db.commit()
    return res.rowcount or 0


async def unread_counts(
    db: AsyncSession,
    *,
    ride_ids: list[int],
    reader_side: RideMessageSender,
    channel: RideMessageChannel = RideMessageChannel.client,
) -> dict[int, int]:
    """Per-ride count of the other party's messages the reader hasn't seen."""
    if not ride_ids:
        return {}
    rows = await db.execute(
        select(RideMessage.ride_id, func.count())
        .where(
            RideMessage.ride_id.in_(ride_ids),
            RideMessage.channel == channel,
            RideMessage.sender == other_side(reader_side),
            RideMessage.read_at.is_(None),
        )
        .group_by(RideMessage.ride_id)
    )
    return {rid: cnt for rid, cnt in rows.all()}


# ── internal channel (ride owner <-> assigned driver) ─────────────────────────
# Both sides write as `driver` (they are staff), so who-said-what and unread are
# resolved by TENANT: my rows are mine, everything else is "the other side".
async def add_internal(
    db: AsyncSession, *, ride_id: int, writer_tenant_id: int, body: str
) -> RideMessage:
    return await add_message(
        db,
        tenant_id=writer_tenant_id,
        ride_id=ride_id,
        sender=RideMessageSender.driver,
        body=body,
        channel=RideMessageChannel.internal,
    )


async def mark_internal_read(
    db: AsyncSession, *, ride_id: int, reader_tenant_id: int, now: dt.datetime | None = None
) -> int:
    """Stamp the OTHER side's internal messages as read."""
    res = await db.execute(
        update(RideMessage)
        .where(
            RideMessage.ride_id == ride_id,
            RideMessage.channel == RideMessageChannel.internal,
            RideMessage.tenant_id != reader_tenant_id,
            RideMessage.read_at.is_(None),
        )
        .values(read_at=now or dt.datetime.now(dt.UTC))
    )
    await db.commit()
    return res.rowcount or 0


async def internal_unread_counts(
    db: AsyncSession, *, ride_ids: list[int], reader_tenant_id: int
) -> dict[int, int]:
    """ride_id -> count of unread internal messages written by the other side."""
    if not ride_ids:
        return {}
    rows = (
        await db.execute(
            select(RideMessage.ride_id, func.count(RideMessage.id))
            .where(
                RideMessage.ride_id.in_(ride_ids),
                RideMessage.channel == RideMessageChannel.internal,
                RideMessage.tenant_id != reader_tenant_id,
                RideMessage.read_at.is_(None),
            )
            .group_by(RideMessage.ride_id)
        )
    ).all()
    return {rid: int(n) for rid, n in rows}


async def post_assignment_note(db: AsyncSession, *, ride: Ride, note: str | None) -> None:
    """Open the internal thread with a line the driver sees first. Best effort: a
    failure here must never undo the assignment itself."""
    text = (note or "").strip()
    body = f"Ride BV-{ride.id} assigned to you." + (f" {text}"[:400] if text else "")
    try:
        await add_internal(db, ride_id=ride.id, writer_tenant_id=ride.tenant_id, body=body)
    except Exception:  # pragma: no cover - defensive
        logger.warning("could not post assignment note for ride %s", ride.id)
