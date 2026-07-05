"""Notifications API (the dashboard bell).

Staff (require_staff) list their tenant's notifications with an unread count,
mark one read, or mark all read. Every query is scoped to the session's tenant;
a notification from another tenant 404s on mark-read (no cross-tenant access).
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.db.base import get_db
from app.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])

LIST_LIMIT = 30


class NotificationOut(BaseModel):
    id: int
    kind: str
    data: dict
    read: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]


@router.get("", response_model=NotificationsOut)
async def list_notifications(
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> NotificationsOut:
    tenant_id = await resolve_tenant_id(db, payload)
    rows = (
        await db.execute(
            select(Notification)
            .where(Notification.tenant_id == tenant_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(LIST_LIMIT)
        )
    ).scalars().all()
    unread = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.tenant_id == tenant_id, Notification.read.is_(False))
        )
    ).scalar_one()
    return NotificationsOut(
        unread=int(unread or 0),
        items=[
            NotificationOut(
                id=n.id, kind=n.kind.value, data=n.data or {}, read=n.read, created_at=n.created_at
            )
            for n in rows
        ],
    )


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = await resolve_tenant_id(db, payload)
    row = (
        await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
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
async def mark_all_read(
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = await resolve_tenant_id(db, payload)
    await db.execute(
        update(Notification)
        .where(Notification.tenant_id == tenant_id, Notification.read.is_(False))
        .values(read=True)
    )
    await db.commit()
    return {"ok": True}
