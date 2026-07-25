"""Per-ride passenger<->driver messaging API.

A rider and their assigned driver exchange messages tied to one ride (the ride
IS the conversation — see ``app.models.ride_message``). Passengers reach it from
/trips; the driver from the ride drawer. The sender side is derived from the
session, never the request body. Posting is allowed only while the ride's chat
window is open (booked through shortly after completion); history stays readable
after it closes.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth, resolve_tenant_id
from app.db.base import get_db
from app.models import (
    Client,
    ClientNotificationKind,
    NotificationKind,
    Ride,
    RideMessage,
    RideMessageChannel,
    RideMessageSender,
)
from app.services import assignment, auth, booking, notifications, push, ratelimit
from app.services import ride_messages as ride_messages_svc

router = APIRouter(tags=["ride-messages"])

MAX_BODY_CHARS = 2000


class RideMessageOut(BaseModel):
    id: int
    sender: str
    body: str
    created_at: dt.datetime


class RideMessagesOut(BaseModel):
    messages: list[RideMessageOut]
    unread: int
    chat_open: bool


class RideMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)


def _out(m: RideMessage) -> RideMessageOut:
    return RideMessageOut(id=m.id, sender=m.sender.value, body=m.body, created_at=m.created_at)


async def _ride_for_chat(
    db: AsyncSession, payload: dict, ride_id: int
) -> tuple[Ride, RideMessageSender]:
    """Load the ride and resolve the viewer's side, enforcing access. A passenger
    may only touch their own ride; staff act as the driver on any ride in their
    tenant (scoped by ``booking.get_ride``)."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if payload.get("role") == auth.ROLE_PASSENGER:
        if ride.client_id is None or ride.client_id != payload.get("cid"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return ride, RideMessageSender.client
    return ride, RideMessageSender.driver


@router.get("/rides/{ride_id}/messages", response_model=RideMessagesOut)
async def list_ride_messages(
    ride_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    after_id: int | None = Query(default=None, ge=0),
) -> RideMessagesOut:
    ride, side = await _ride_for_chat(db, payload, ride_id)
    msgs = await ride_messages_svc.list_messages(db, ride_id=ride.id, after_id=after_id)
    # Opening the thread marks the other party's messages read (clears my unread).
    await ride_messages_svc.mark_read(db, ride_id=ride.id, reader_side=side)
    return RideMessagesOut(
        messages=[_out(m) for m in msgs],
        unread=0,
        chat_open=booking.chat_window_open(ride),
    )


@router.post(
    "/rides/{ride_id}/messages",
    response_model=RideMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_ride_message(
    ride_id: int,
    body: RideMessageIn,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
) -> RideMessageOut:
    ride, side = await _ride_for_chat(db, payload, ride_id)
    if not booking.chat_window_open(ride):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="chat_closed")

    text = body.body.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="empty_message"
        )

    ident = payload.get("cid") if side == RideMessageSender.client else ride.tenant_id
    key = f"ridemsg:{ride.id}:{side.value}:{ident}"
    if not ratelimit.allow(key + ":m", limit=10, window_seconds=60) or not ratelimit.allow(
        key + ":h", limit=60, window_seconds=3600
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="chat_rate_limited"
        )

    msg = await ride_messages_svc.add_message(
        db, tenant_id=ride.tenant_id, ride_id=ride.id, sender=side, body=text
    )

    # Best-effort fan-out AFTER the message is committed (never breaks the send).
    if side == RideMessageSender.client:
        name = ""
        if ride.client_id:
            client = (
                await db.execute(select(Client).where(Client.id == ride.client_id))
            ).scalar_one_or_none()
            if client and client.name:
                name = client.name.split(" ")[0]
        await notifications.emit(
            db,
            tenant_id=ride.assigned_tenant_id or ride.tenant_id,
            kind=NotificationKind.ride_message,
            data={"ride_id": ride.id, "client_name": name, "snippet": text[:80]},
        )
    else:
        push.notify_client(
            ride.tenant_id,
            ride.client_id,
            event="ride_message",
            lang=ride.lang,
            ride_id=ride.id,
        )
        await notifications.emit_client(
            db,
            client_id=ride.client_id,
            tenant_id=ride.tenant_id,
            kind=ClientNotificationKind.ride_message,
            data={"ride_id": ride.id, "snippet": text[:80]},
        )

    return _out(msg)


# ── internal channel: ride owner <-> assigned driver ──────────────────────────
class InternalMessageOut(BaseModel):
    id: int
    body: str
    mine: bool  # written by MY tenant (both sides are staff, so sender can't tell)
    created_at: dt.datetime
    read_at: dt.datetime | None = None


class InternalThreadOut(BaseModel):
    messages: list[InternalMessageOut]
    unread: int = 0
    can_write: bool = False


async def _ride_for_internal(db: AsyncSession, payload: dict, ride_id: int) -> tuple[Ride, int]:
    """Load a ride whose internal thread the caller may use: STAFF only, and only the
    ride's owner or the driver it was assigned to. A passenger is never allowed here —
    this thread is where the owner and driver talk about their trip."""
    if payload.get("role") == auth.ROLE_PASSENGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if not assignment.can_view(ride, tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return ride, tenant_id


@router.get("/rides/{ride_id}/internal-messages", response_model=InternalThreadOut)
async def list_internal_messages(
    ride_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    after_id: int | None = Query(default=None, ge=0),
) -> InternalThreadOut:
    ride, tenant_id = await _ride_for_internal(db, payload, ride_id)
    msgs = await ride_messages_svc.list_messages(
        db,
        ride_id=ride.id,
        after_id=after_id,
        channel=RideMessageChannel.internal,
    )
    await ride_messages_svc.mark_internal_read(db, ride_id=ride.id, reader_tenant_id=tenant_id)
    return InternalThreadOut(
        messages=[
            InternalMessageOut(
                id=m.id,
                body=m.body,
                mine=m.tenant_id == tenant_id,
                created_at=m.created_at,
                read_at=m.read_at,
            )
            for m in msgs
        ],
        unread=0,
        # Once the ride is handed back there is nobody on the other end.
        can_write=ride.assigned_tenant_id is not None,
    )


@router.post(
    "/rides/{ride_id}/internal-messages",
    response_model=InternalMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_internal_message(
    ride_id: int,
    body: RideMessageIn,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
) -> InternalMessageOut:
    """Owner<->assigned-driver message about this ride. Same rate limits as the
    passenger thread so a stuck client can't hammer it."""
    ride, tenant_id = await _ride_for_internal(db, payload, ride_id)
    if ride.assigned_tenant_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ride_not_assigned")
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_message")
    key = f"ridemsg:internal:{ride.id}:{tenant_id}"
    if not ratelimit.allow(key + ":m", limit=10, window_seconds=60) or not ratelimit.allow(
        key + ":h", limit=60, window_seconds=3600
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="chat_rate_limited"
        )
    msg = await ride_messages_svc.add_internal(
        db, ride_id=ride.id, writer_tenant_id=tenant_id, body=text
    )
    # Ping the OTHER staff side: owner -> assigned driver, or driver -> owner.
    other = ride.assigned_tenant_id if tenant_id == ride.tenant_id else ride.tenant_id
    await notifications.emit(
        db,
        tenant_id=other,
        kind=NotificationKind.ride_message,
        data={"ride_id": ride.id, "internal": True, "snippet": text[:80]},
    )
    push.notify_staff(other, kind="ride_message")
    return InternalMessageOut(
        id=msg.id, body=msg.body, mine=True, created_at=msg.created_at, read_at=msg.read_at
    )
