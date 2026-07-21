"""In-app staff notifications — emit + prune.

``emit`` records a notification for a driver tenant. It is BEST-EFFORT and must
never break the caller (same contract as the notification emails): it commits
its own row in a try/except and rolls back only on its own failure. Call it AFTER
the caller has committed its own work, so a notification failure can never lose or
corrupt the ride / message / review that triggered it.

Per-tenant retention is capped at ``KEEP_PER_TENANT`` newest rows so the table
never grows without bound.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClientNotification, ClientNotificationKind, Notification, NotificationKind

log = logging.getLogger("blackvolt.notifications")

KEEP_PER_TENANT = 100
KEEP_PER_CLIENT = 50


async def emit(
    db: AsyncSession,
    *,
    tenant_id: int | None,
    kind: NotificationKind,
    data: dict | None = None,
) -> None:
    """Record one notification for ``tenant_id``. No-op when tenant_id is falsy.
    Never raises."""
    if not tenant_id:
        return
    try:
        # Savepoint so a notification failure rolls back ONLY the notification
        # insert/prune, never any pending work the caller left on the session.
        async with db.begin_nested():
            db.add(Notification(tenant_id=tenant_id, kind=kind, data=data or {}))
            await db.flush()
            await _prune(db, tenant_id)
        await db.commit()
        # Mirror the bell to a Web Push for staff devices. Fire-and-forget; never raises.
        from app.services import push

        push.notify_staff(tenant_id, kind=kind.value)
    except Exception:  # noqa: BLE001 — a notification must never break the caller
        log.warning("notification emit failed (tenant=%s kind=%s)", tenant_id, kind, exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _prune(db: AsyncSession, tenant_id: int) -> None:
    """Keep only the newest KEEP_PER_TENANT rows for the tenant."""
    keep_ids = (
        select(Notification.id)
        .where(Notification.tenant_id == tenant_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(KEEP_PER_TENANT)
        .scalar_subquery()
    )
    await db.execute(
        delete(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.id.not_in(keep_ids),
        )
    )


async def emit_client(
    db: AsyncSession,
    *,
    client_id: int | None,
    tenant_id: int | None,
    kind: ClientNotificationKind,
    data: dict | None = None,
) -> None:
    """Record one in-app notification for a passenger (the client bell). No-op
    when client_id/tenant_id is falsy. Never raises — same best-effort contract as
    :func:`emit`. Unlike ``emit`` it does NOT send a push: every caller already
    fires ``push.notify_client`` for these events, so pushing here would
    double-notify the passenger."""
    if not client_id or not tenant_id:
        return
    try:
        # Savepoint so a notification failure rolls back ONLY this insert/prune,
        # never any pending work the caller left on the session.
        async with db.begin_nested():
            db.add(
                ClientNotification(
                    client_id=client_id, tenant_id=tenant_id, kind=kind, data=data or {}
                )
            )
            await db.flush()
            await _prune_client(db, client_id)
        await db.commit()
    except Exception:  # noqa: BLE001 — a notification must never break the caller
        log.warning(
            "client notification emit failed (client=%s kind=%s)", client_id, kind, exc_info=True
        )
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _prune_client(db: AsyncSession, client_id: int) -> None:
    """Keep only the newest KEEP_PER_CLIENT rows for the client."""
    keep_ids = (
        select(ClientNotification.id)
        .where(ClientNotification.client_id == client_id)
        .order_by(ClientNotification.created_at.desc(), ClientNotification.id.desc())
        .limit(KEEP_PER_CLIENT)
        .scalar_subquery()
    )
    await db.execute(
        delete(ClientNotification).where(
            ClientNotification.client_id == client_id,
            ClientNotification.id.not_in(keep_ids),
        )
    )
