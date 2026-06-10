"""FastAPI auth dependencies built on the HMAC session cookie."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.models import AllowedUser
from app.models.allowed_user import ROLE_ADMIN
from app.services import auth
from app.services.tenancy import get_default_tenant


def current_payload(request: Request) -> dict | None:
    """Decode the session cookie → payload, or None."""
    return auth.decode_token(request.cookies.get(auth.COOKIE_NAME))


def require_auth(request: Request) -> dict:
    """Any valid session. When AUTH_ENABLED is false, allow through with a
    synthetic owner payload (dev/open mode)."""
    settings = get_settings()
    payload = current_payload(request)
    if payload is not None:
        return payload
    if not settings.AUTH_ENABLED:
        return {"role": auth.ROLE_OWNER, "tid": None, "open": True}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")


def require_staff(payload: dict = Depends(require_auth)) -> dict:
    """Owner or driver only (the dashboard audience)."""
    if get_settings().AUTH_ENABLED and payload.get("role") not in auth.STAFF_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return payload


async def session_is_admin(db: AsyncSession, payload: dict | None) -> bool:
    """Whether a session is a super-admin. True when: its email is a pinned admin
    (GOOGLE_ADMIN_EMAILS); OR it's the owner of the default (Black Volt) tenant —
    the master/password session (also recovers tokens minted before the `adm`
    flag existed); OR the token claims `adm` AND the live allow-list row is still
    active + admin. Open mode (AUTH_ENABLED=false) is treated as admin (dev).
    Drivers own a different tenant → never elevated.

    The `adm` claim is re-checked against the DB (not trusted blindly) so that
    demoting or deactivating an admin revokes their access immediately rather than
    only when their week-long session token expires."""
    if not get_settings().AUTH_ENABLED:
        return True
    if not payload:
        return False
    email = (payload.get("email") or "").lower().strip()
    if email and email in get_settings().google_admin_emails_list:
        return True
    if payload.get("role") == auth.ROLE_OWNER and payload.get("cid") is None:
        if payload.get("tid") == (await get_default_tenant(db)).id:
            return True
    if payload.get("adm") and email:
        row = (
            await db.execute(select(AllowedUser).where(AllowedUser.email == email))
        ).scalar_one_or_none()
        if row is not None and row.active and row.role == ROLE_ADMIN:
            return True
    return False


async def require_admin(
    payload: dict = Depends(require_auth), db: AsyncSession = Depends(get_db)
) -> dict:
    """Super-admin only (the access-list / Team panel). No-op in open mode."""
    if not await session_is_admin(db, payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admins_only")
    return payload


async def resolve_tenant_id(db: AsyncSession, payload: dict | None) -> int:
    """Tenant id from the session, falling back to the single default tenant
    (single-driver MVP / open mode where the token carries no tenant)."""
    if payload and payload.get("tid"):
        return int(payload["tid"])
    return (await get_default_tenant(db)).id
