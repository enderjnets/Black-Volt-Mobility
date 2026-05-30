"""FastAPI auth dependencies built on the HMAC session cookie."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.config import get_settings
from app.services import auth


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
