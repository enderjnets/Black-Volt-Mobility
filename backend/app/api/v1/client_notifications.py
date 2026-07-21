"""Client (passenger) notifications API — the passenger bell.

A signed-in passenger (``require_passenger``) lists their own notifications with
an unread count, marks one read, or marks all read. Every query is scoped to the
session's ``client_id`` (the ``cid`` claim), so one passenger can never see or
mutate another's notifications. Mirrors ``api/v1/notifications.py`` (the staff
bell) but keyed on client_id instead of tenant_id.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_passenger
from app.db.base import get_db
from app.models import ClientNotification

router = APIRouter(prefix="/client/notifications", tags=["client-notifications"])

LIST_LIMIT = 30


class ClientNotificationOut(BaseModel):
    id: int
    kind: str
    data: dict
    read: bool
    created_at: dt.datetime


class ClientNotificationsOut(BaseModel):
    unread: int
    items: list[ClientNotificationOut]


def _cid(payload: dict) -> int:
    return int(payload["cid"])


@router.get("", response_model=ClientNotificationsOut)
async def list_client_notifications(
    payload: dict = Depends(require_passenger),
    db: AsyncSession = Depends(get_db),
) -> ClientNotificationsOut:
    cid = _cid(payload)
    rows = (
        await db.execute(
            select(ClientNotification)
            .where(ClientNotification.client_id == cid)
            .order_by(ClientNotification.created_at.desc(), ClientNotification.id.desc())
            .limit(LIST_LIMIT)
        )
    ).scalars().all()
    unread = (
        await db.execute(
            select(func.count())
            .select_from(ClientNotification)
            .where(ClientNotification.client_id == cid, ClientNotification.read.is_(False))
        )
    ).scalar_one()
    return ClientNotificationsOut(
        unread=int(unread or 0),
        items=[
            ClientNotificationOut(
                id=n.id, kind=n.kind.value, data=n.data or {}, read=n.read, created_at=n.created_at
            )
            for n in rows
        ],
    )


@router.post("/{notification_id}/read")
async def mark_client_read(
    notification_id: int,
    payload: dict = Depends(require_passenger),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cid = _cid(payload)
    row = (
        await db.execute(
            select(ClientNotification).where(
                ClientNotification.id == notification_id,
                ClientNotification.client_id == cid,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="notification_not_found"
        )
    if not row.read:
        row.read = True
        await db.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all_client_read(
    payload: dict = Depends(require_passenger),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cid = _cid(payload)
    await db.execute(
        update(ClientNotification)
        .where(ClientNotification.client_id == cid, ClientNotification.read.is_(False))
        .values(read=True)
    )
    await db.commit()
    return {"ok": True}
