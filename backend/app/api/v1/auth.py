"""Auth endpoints: owner password login, passenger Google login, me, logout."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import session_is_admin
from app.config import get_settings
from app.db.base import get_db
from app.models.allowed_user import ROLE_ADMIN
from app.services import auth, profile
from app.services.tenancy import (
    create_tenant_for,
    find_client_by_google_sub,
    find_or_create_client,
    get_default_tenant,
    get_tenant,
    resolve_referral_tenant,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=auth.COOKIE_NAME,
        value=token,
        max_age=settings.AUTH_TTL_HOURS * 3600,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


class PasswordLogin(BaseModel):
    password: str


@router.post("/login")
async def login_password(
    body: PasswordLogin, response: Response, db: AsyncSession = Depends(get_db)
):
    """Owner master login with the shared dashboard password → super-admin of the
    Black Volt tenant."""
    if not auth.check_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_password")
    tenant = await get_default_tenant(db)
    token = auth.make_token(role=auth.ROLE_OWNER, tenant_id=tenant.id, is_admin=True)
    _set_cookie(response, token)
    return {"ok": True, "role": auth.ROLE_OWNER, "tenant": tenant.slug}


class GoogleLogin(BaseModel):
    id_token: str
    # Driver slug from the referral link (`/d/{slug}`). Only used to attribute a
    # brand-new passenger to the driver who brought them; ignored once the account
    # already has a designated driver (first-touch is permanent).
    ref: str | None = None


@router.post("/login/google")
async def login_google(body: GoogleLogin, response: Response, db: AsyncSession = Depends(get_db)):
    """Google login. Allow-listed emails (admin or active driver) sign into the
    dashboard as the OWNER of their own tenant — provisioned on first sign-in.
    Everyone else becomes a passenger (their Client is find-or-created)."""
    try:
        info = auth.verify_google_id_token(body.id_token)
    except auth.GoogleAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    email = info["email"]

    allowed = await auth.resolve_user_access(db, email)
    if allowed is not None:
        allowed.last_login = datetime.now(UTC)
        # Auto-provision this driver's own workspace the first time they sign in.
        if allowed.tenant_id is None:
            t = await create_tenant_for(db, name=info["name"] or email.split("@")[0])
            allowed.tenant_id = t.id
        await db.commit()
        is_admin = allowed.role == ROLE_ADMIN
        token = auth.make_token(
            role=auth.ROLE_OWNER, tenant_id=allowed.tenant_id, email=email, is_admin=is_admin
        )
        _set_cookie(response, token)
        their_tenant = await get_tenant(db, allowed.tenant_id)
        return {
            "ok": True,
            "role": auth.ROLE_OWNER,
            "tenant": their_tenant.slug if their_tenant else None,
            "email": email,
            "is_admin": is_admin,
        }

    # Not on the access list (or deactivated) → passenger. Designated-driver rule:
    # if this Google account already exists under any driver, keep that driver
    # (first-touch, permanent); otherwise attribute to the referral link's driver,
    # falling back to the default Black Volt tenant.
    existing = await find_client_by_google_sub(db, info["sub"])
    if existing is not None:
        tenant_id = existing.tenant_id
    else:
        tenant_id = (await resolve_referral_tenant(db, body.ref)).id
    given, family = info.get("given_name") or "", info.get("family_name") or ""
    full_name = info["name"] or f"{given} {family}".strip() or None
    client = await find_or_create_client(
        db, tenant_id=tenant_id, google_sub=info["sub"], email=email, name=full_name,
        first_name=given or None, last_name=family or None,
    )
    token = auth.make_token(
        role=auth.ROLE_PASSENGER, tenant_id=tenant_id, email=email, client_id=client.id
    )
    _set_cookie(response, token)
    return {
        "ok": True,
        "role": auth.ROLE_PASSENGER,
        "client": {"id": client.id, "name": client.name, "email": client.email},
        "profile_complete": profile.is_complete(client),
    }


@router.get("/me")
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    """Current session + public config (google_client_id, auth_enabled)."""
    settings = get_settings()
    payload = auth.decode_token(request.cookies.get(auth.COOKIE_NAME))
    base = {
        "authenticated": payload is not None,
        "auth_enabled": settings.AUTH_ENABLED,
        "google_signin_enabled": bool(settings.GOOGLE_CLIENT_ID),
        "google_client_id": settings.GOOGLE_CLIENT_ID or None,
    }
    if payload is None:
        return base
    tid = payload.get("tid")
    tenant = await get_tenant(db, tid) if tid else None
    base.update(
        {
            "role": payload.get("role"),
            "email": payload.get("email"),
            "client_id": payload.get("cid"),
            "tenant_id": tid,
            # Slug of the session's tenant — for a passenger this is their
            # designated driver, so the "Your Driver" tab can resolve the profile.
            "tenant_slug": tenant.slug if tenant else None,
            "is_admin": await session_is_admin(db, payload),
        }
    )
    cid = payload.get("cid")
    if cid is not None:
        from sqlalchemy import select

        from app.models import Client
        from app.services import profile as profile_svc

        client = (
            await db.execute(select(Client).where(Client.id == int(cid)))
        ).scalar_one_or_none()
        base["profile_complete"] = profile_svc.is_complete(client) if client else False
    return base


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}
