"""Per-user Google Calendar connection (OAuth authorization-code, self-service).

A team member links their own Google Calendar so their rides sync to *their*
calendar instead of the shared Black Volt one. Flow:

  POST /calendar/connect   → {auth_url}   (consent URL, signed CSRF `state`)
  GET  /calendar/callback  → exchange code → store encrypted refresh token →
                             302 back to /dashboard/settings?calendar=…
  GET  /calendar/connection→ status for the Settings card
  POST /calendar/disconnect→ revoke at Google + delete the stored credential

Security: scope is the minimum `calendar.events`; the refresh token is stored
**encrypted** (Fernet); `state` is HMAC-signed + time-boxed and bound to the
session's tenant; the tenant is always taken from the session (never the body),
matching the IDOR-safe pattern in `me.py`. The connect flow is staff-only.
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    current_payload,
    require_staff,
    resolve_tenant_id,
    session_is_admin,
)
from app.config import get_settings
from app.db.base import get_db
from app.models import CalendarCredential
from app.services import auth, crypto

# Google sometimes returns granted scopes in a different order/superset than
# requested (openid is auto-added), which otherwise trips oauthlib's strict
# scope check. Relax it so the exchange succeeds.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

logger = logging.getLogger("blackvolt.calendar_link")

router = APIRouter(prefix="/calendar", tags=["calendar"])

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
]


def _flow(state: str | None = None):
    settings = get_settings()
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.calendar_oauth_redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=_SCOPES, state=state)
    flow.redirect_uri = settings.calendar_oauth_redirect_uri
    return flow


def _settings_url(suffix: str) -> str:
    base = get_settings().PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/dashboard/settings?calendar={suffix}"


@router.get("/connection")
async def connection(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Connection status for the session's tenant (drives the Settings card)."""
    settings = get_settings()
    is_admin = await session_is_admin(db, payload)
    tenant_id = await resolve_tenant_id(db, payload)
    cred = (
        await db.execute(
            select(CalendarCredential).where(CalendarCredential.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    return {
        "connected": cred is not None,
        "google_email": cred.google_email if cred else None,
        "calendar_id": cred.calendar_id if cred else None,
        "connected_at": cred.connected_at.isoformat() if cred and cred.connected_at else None,
        # Admins use the shared Black Volt calendar — they don't need to connect.
        "is_admin": is_admin,
        "oauth_configured": settings.calendar_oauth_configured,
    }


@router.post("/connect")
async def connect(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Return the Google consent URL. The session's tenant is embedded in a
    signed `state` so the callback can bind the credential to the right tenant."""
    settings = get_settings()
    if not settings.calendar_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="calendar_oauth_unconfigured"
        )
    tenant_id = await resolve_tenant_id(db, payload)
    state = auth.sign_state({"tid": tenant_id, "n": secrets.token_urlsafe(8)})
    flow = _flow(state=state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # force a refresh_token even on re-consent
    )
    return {"auth_url": auth_url}


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """OAuth redirect target. Verifies the signed state + session, exchanges the
    code, stores the encrypted refresh token, and redirects back to Settings.
    Always redirects (never returns a raw error) so the user lands in the app."""
    settings = get_settings()
    if error or not code or not state:
        return RedirectResponse(_settings_url("error"), status_code=302)

    st = auth.verify_state(state)
    if not st:
        return RedirectResponse(_settings_url("error"), status_code=302)

    # Bind to the current session's tenant (defense-in-depth vs a replayed state).
    payload = current_payload(request)
    if payload is None and settings.AUTH_ENABLED:
        return RedirectResponse(_settings_url("error"), status_code=302)
    sess_tid = await resolve_tenant_id(db, payload)
    if int(st.get("tid", -1)) != int(sess_tid):
        return RedirectResponse(_settings_url("error"), status_code=302)

    try:
        flow = _flow(state=state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        refresh_token = creds.refresh_token
        if not refresh_token:
            # No refresh token (user previously consented and Google withheld it).
            return RedirectResponse(_settings_url("error"), status_code=302)
        google_email = _connected_email(creds)
        enc = crypto.encrypt(refresh_token)
    except Exception as e:  # noqa: BLE001 — surface as a friendly redirect
        logger.warning("calendar oauth exchange failed for tenant %s: %s", sess_tid, e)
        return RedirectResponse(_settings_url("error"), status_code=302)

    cred = (
        await db.execute(
            select(CalendarCredential).where(CalendarCredential.tenant_id == sess_tid)
        )
    ).scalar_one_or_none()
    if cred is None:
        cred = CalendarCredential(tenant_id=sess_tid)
        db.add(cred)
    cred.refresh_token_enc = enc
    cred.google_email = google_email
    cred.calendar_id = "primary"
    cred.scopes = " ".join(_SCOPES)
    await db.commit()
    return RedirectResponse(_settings_url("connected"), status_code=302)


@router.post("/disconnect")
async def disconnect(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Revoke at Google (best-effort) and delete the stored credential."""
    tenant_id = await resolve_tenant_id(db, payload)
    cred = (
        await db.execute(
            select(CalendarCredential).where(CalendarCredential.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if cred is not None:
        try:
            import requests

            token = crypto.decrypt(cred.refresh_token_enc)
            requests.post(
                "https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=10
            )
        except Exception as e:  # noqa: BLE001 — revoke is best-effort
            logger.warning("calendar revoke failed for tenant %s: %s", tenant_id, e)
        await db.delete(cred)
        await db.commit()
    return {"ok": True, "connected": False}


def _connected_email(creds) -> str | None:
    """Best-effort: read the connected account email from the id_token. Returns
    None on any failure — the email is display-only, never a secret."""
    token = getattr(creds, "id_token", None)
    if not token:
        return None
    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token as google_id_token

        info = google_id_token.verify_oauth2_token(
            token, ga_requests.Request(), get_settings().GOOGLE_OAUTH_CLIENT_ID
        )
        return info.get("email")
    except Exception:  # noqa: BLE001
        return None
