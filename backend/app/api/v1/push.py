"""Web Push subscription endpoints (PWA notifications).

- ``GET  /push/config``      → public: {enabled, public_key} for the browser to
                               build its PushSubscription (applicationServerKey).
- ``POST /push/subscribe``   → any signed-in session registers/refreshes a device.
- ``POST /push/unsubscribe`` → drop a device by its endpoint.
- ``POST /push/test``        → staff only: send a test push to your own devices,
                               so the owner can verify end-to-end without creating
                               a real ride (Square is LIVE — never fake bookings).

Audience is derived from the session, never trusted from the client: staff roles
→ ``staff`` subscriptions; a signed-in passenger (``cid``) → ``client``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth, require_staff, resolve_tenant_id
from app.config import get_settings
from app.db.base import get_db
from app.models import PushSubscription
from app.services import auth, push

router = APIRouter(prefix="/push", tags=["push"])


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=500)
    auth: str = Field(min_length=1, max_length=500)


class SubscribeBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
    # Web Push keys — required for "webpush", omitted for "fcm" (the native app,
    # whose registration token lives in `endpoint`).
    keys: PushKeys | None = None
    platform: str = Field(default="webpush", pattern="^(webpush|fcm)$")


class UnsubscribeBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)


@router.get("/config")
async def push_config() -> dict:
    """Public: whether *Web Push* is enabled and the VAPID public key for the
    browser. (FCM for the native app doesn't use this endpoint — the app gets its
    token from the OS.)"""
    s = get_settings()
    web_enabled = bool(s.VAPID_PUBLIC_KEY and s.VAPID_PRIVATE_KEY)
    return {"enabled": web_enabled, "public_key": s.VAPID_PUBLIC_KEY}


@router.post("/subscribe")
async def subscribe(
    body: SubscribeBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
) -> dict:
    """Register (or refresh) the caller's device push subscription. Idempotent by
    endpoint: the same device re-subscribing updates its keys in place."""
    role = payload.get("role")
    cid = payload.get("cid")
    if role == auth.ROLE_PASSENGER and cid:
        audience, client_id = "client", int(cid)
        tid = payload.get("tid")
        tenant_id = int(tid) if tid else await resolve_tenant_id(db, payload)
    else:
        # Staff (owner/driver) or dev open-mode → staff audience.
        audience, client_id = "staff", None
        tenant_id = await resolve_tenant_id(db, payload)

    if body.platform == "webpush" and body.keys is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="missing_keys")
    p256dh = body.keys.p256dh if body.keys else None
    auth_k = body.keys.auth if body.keys else None

    ua = (request.headers.get("user-agent") or "")[:300] or None
    # Atomic upsert by endpoint (the browser/app mints one per device) —
    # concurrency-safe, so a double-tap can't 500 on the unique constraint.
    values = {
        "tenant_id": tenant_id,
        "audience": audience,
        "platform": body.platform,
        "client_id": client_id,
        "endpoint": body.endpoint,
        "p256dh": p256dh,
        "auth": auth_k,
        "ua": ua,
    }
    stmt = pg_insert(PushSubscription).values(**values).on_conflict_do_update(
        index_elements=[PushSubscription.endpoint],
        set_={
            "tenant_id": tenant_id,
            "audience": audience,
            "platform": body.platform,
            "client_id": client_id,
            "p256dh": p256dh,
            "auth": auth_k,
            "ua": ua,
        },
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True, "audience": audience}


@router.post("/unsubscribe")
async def unsubscribe(
    body: UnsubscribeBody,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
) -> dict:
    """Remove a device subscription by endpoint. Scoped to the caller's tenant as
    defense-in-depth so one session can never delete another tenant's subscription."""
    tenant_id = await resolve_tenant_id(db, payload)
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.tenant_id == tenant_id,
        )
    )
    await db.commit()
    return {"ok": True}


@router.post("/test")
async def test_push(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
) -> dict:
    """Send a test push to the caller tenant's staff devices."""
    if not get_settings().push_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="push_disabled")
    tenant_id = await resolve_tenant_id(db, payload)
    _found, sent = await push.deliver_to_staff(
        tenant_id,
        {
            "title": "Black Volt",
            "body": "Push notifications are working.",
            "url": "/dashboard",
            "tag": "test",
        },
    )
    return {"ok": True, "sent": sent}
