"""Data access for per-ride passenger<->driver messages.

Thin query helpers over ``RideMessage``; the ride's tenant and the viewer's
identity are resolved and authorized by the API layer. Unread is always a live
COUNT of the other party's still-unread messages — opening a thread stamps
``read_at`` on them, so there is no counter to desync.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RideMessage, RideMessageSender


def other_side(side: RideMessageSender) -> RideMessageSender:
    return (
        RideMessageSender.driver
        if side == RideMessageSender.client
        else RideMessageSender.client
    )


async def list_messages(
    db: AsyncSession, *, ride_id: int, after_id: int | None = None, limit: int = 200
) -> list[RideMessage]:
    q = select(RideMessage).where(RideMessage.ride_id == ride_id)
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
) -> RideMessage:
    msg = RideMessage(tenant_id=tenant_id, ride_id=ride_id, sender=sender, body=body)
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
) -> int:
    """Stamp ``read_at`` on the messages written by the OTHER party. Returns how
    many were newly marked (0 when the reader was already caught up)."""
    res = await db.execute(
        update(RideMessage)
        .where(
            RideMessage.ride_id == ride_id,
            RideMessage.sender == other_side(reader_side),
            RideMessage.read_at.is_(None),
        )
        .values(read_at=now or dt.datetime.now(dt.UTC))
    )
    await db.commit()
    return res.rowcount or 0


async def unread_counts(
    db: AsyncSession, *, ride_ids: list[int], reader_side: RideMessageSender
) -> dict[int, int]:
    """Per-ride count of the other party's messages the reader hasn't seen."""
    if not ride_ids:
        return {}
    rows = await db.execute(
        select(RideMessage.ride_id, func.count())
        .where(
            RideMessage.ride_id.in_(ride_ids),
            RideMessage.sender == other_side(reader_side),
            RideMessage.read_at.is_(None),
        )
        .group_by(RideMessage.ride_id)
    )
    return {rid: cnt for rid, cnt in rows.all()}
