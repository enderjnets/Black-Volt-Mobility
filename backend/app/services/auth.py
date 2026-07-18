"""Auth — HMAC-signed session cookie (no JWT dep) with two audiences:

  • OWNER/DRIVER  → a shared `DASHBOARD_PASSWORD` (the driver logs into the
    dashboard on app.blackvoltmobility.com). Token role = "owner".
  • PASSENGER     → Google Sign-In. We verify the Google ID token, find-or-create
    a Client row for the tenant, and mint a "passenger" token carrying client_id.

Tokens carry {sub, exp, role, tid, email?, cid?}. The signing secret is
AUTH_SECRET if set, else derived from the password (stable across restarts).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

COOKIE_NAME = "bv_auth"
_SUBJECT = "blackvolt"

ROLE_OWNER = "owner"
ROLE_DRIVER = "driver"
ROLE_PASSENGER = "passenger"
STAFF_ROLES = {ROLE_OWNER, ROLE_DRIVER}


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _secret() -> bytes:
    s = get_settings()
    material = s.AUTH_SECRET or f"blackvolt-auth::{s.DASHBOARD_PASSWORD}"
    return hashlib.sha256(material.encode("utf-8")).digest()


def check_password(password: str) -> bool:
    """Constant-time compare against DASHBOARD_PASSWORD (False if none set)."""
    expected = get_settings().DASHBOARD_PASSWORD
    if not expected:
        return False
    return hmac.compare_digest(password or "", expected)


def make_token(
    *,
    role: str,
    tenant_id: int,
    email: str | None = None,
    client_id: int | None = None,
    is_admin: bool = False,
    ttl_hours: int | None = None,
) -> str:
    s = get_settings()
    ttl = ttl_hours if ttl_hours is not None else s.AUTH_TTL_HOURS
    payload: dict = {
        "sub": _SUBJECT,
        "exp": int(time.time()) + ttl * 3600,
        "role": role,
        "tid": tenant_id,
    }
    if email:
        payload["email"] = email
    if client_id is not None:
        payload["cid"] = client_id
    if is_admin:
        payload["adm"] = True
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())
    return f"{payload_b64}.{sig}"


def decode_token(token: str | None) -> dict | None:
    """Return the verified payload (sig + sub + exp ok), else None."""
    if not token or "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    expected = _b64e(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        return None
    if payload.get("sub") != _SUBJECT:
        return None
    if int(payload.get("exp", 0)) <= int(time.time()):
        return None
    return payload


# ─── Signed short-lived state (OAuth CSRF) ───────────────────────────────────
def sign_state(data: dict, *, ttl_seconds: int = 600) -> str:
    """Sign a short-lived state blob for the OAuth connect flow. Tamper-evident
    (HMAC over the same secret as session tokens) and time-boxed via `exp`."""
    payload = dict(data)
    payload["exp"] = int(time.time()) + ttl_seconds
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())
    return f"{payload_b64}.{sig}"


def verify_state(token: str | None) -> dict | None:
    """Return the verified state payload (signature + non-expired), else None."""
    if not token or "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    expected = _b64e(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        return None
    if int(payload.get("exp", 0)) <= int(time.time()):
        return None
    return payload


# ─── Google Sign In ──────────────────────────────────────────────────────
class GoogleAuthError(Exception):
    """Raised when Google ID token verification fails."""


def verify_google_id_token(id_token_str: str) -> dict:
    """Validate a Google ID token; return {email, sub, name, given_name, family_name}.

    Checks signature against Google's keys, that `aud` is one of the accepted
    client IDs (web + native), and that the email is verified. Raises
    GoogleAuthError otherwise.
    """
    s = get_settings()
    accepted = s.google_client_ids_list
    if not accepted:
        raise GoogleAuthError("google_signin_not_configured")
    if not id_token_str:
        raise GoogleAuthError("missing_id_token")
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError as e:
        raise GoogleAuthError(f"google_auth_library_missing: {e}") from e
    try:
        # Verify signature/issuer/expiry without pinning a single audience, then
        # check `aud` against the accepted set ourselves (web + native client IDs).
        claims = google_id_token.verify_oauth2_token(id_token_str, google_requests.Request())
    except ValueError as e:
        raise GoogleAuthError(f"invalid_id_token: {e}") from e
    if claims.get("aud") not in accepted:
        raise GoogleAuthError("audience_mismatch")
    if not claims.get("email_verified"):
        raise GoogleAuthError("email_not_verified")
    email = (claims.get("email") or "").lower().strip()
    sub = claims.get("sub") or ""
    if not email or not sub:
        raise GoogleAuthError("missing_email_or_sub")
    return {
        "email": email,
        "sub": sub,
        "name": claims.get("name") or "",
        "given_name": claims.get("given_name") or "",
        "family_name": claims.get("family_name") or "",
    }


# ─── Access list (DB-backed allow-list for the dashboard) ────────────────────
async def resolve_user_access(db: AsyncSession, email: str):
    """Return the `AllowedUser` a verified email may sign into the dashboard as,
    or None to deny. Precedence:
      1. env GOOGLE_ADMIN_EMAILS → admin (immutable bootstrap; row ensured).
      2. allowed_users row that is `active` → its role/tenant.
      3. otherwise → None (denied; the caller falls back to passenger).
    """
    from app.models import AllowedUser
    from app.models.allowed_user import ROLE_ADMIN
    from app.services.tenancy import get_default_tenant

    email = (email or "").lower().strip()
    if not email:
        return None
    row = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()

    if email in get_settings().google_admin_emails_list:
        # Pinned super-admin: ensure an active admin row tied to the default tenant.
        if row is None:
            tenant = await get_default_tenant(db)
            row = AllowedUser(
                email=email, role=ROLE_ADMIN, active=True,
                tenant_id=tenant.id, added_by="bootstrap",
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
        elif row.role != ROLE_ADMIN or not row.active or row.tenant_id is None:
            row.role = ROLE_ADMIN
            row.active = True
            if row.tenant_id is None:
                row.tenant_id = (await get_default_tenant(db)).id
            await db.commit()
            await db.refresh(row)
        return row

    return row if (row is not None and row.active) else None
