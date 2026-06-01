"""Auth endpoints: owner password login, passenger Google login, me, logout."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db
from app.services import auth
from app.services.tenancy import find_or_create_client, get_default_tenant

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
    """Owner/driver login with the shared dashboard password."""
    if not auth.check_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_password")
    tenant = await get_default_tenant(db)
    token = auth.make_token(role=auth.ROLE_OWNER, tenant_id=tenant.id)
    _set_cookie(response, token)
    return {"ok": True, "role": auth.ROLE_OWNER, "tenant": tenant.slug}


class GoogleLogin(BaseModel):
    id_token: str


@router.post("/login/google")
async def login_google(body: GoogleLogin, response: Response, db: AsyncSession = Depends(get_db)):
    """Google login. Allow-listed emails (GOOGLE_ADMIN_EMAILS) sign in as the
    driver/owner of the dashboard; everyone else becomes a passenger (their
    Client is find-or-created)."""
    try:
        info = auth.verify_google_id_token(body.id_token)
    except auth.GoogleAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    tenant = await get_default_tenant(db)
    email = info["email"]

    if email in get_settings().google_admin_emails_list:
        token = auth.make_token(role=auth.ROLE_OWNER, tenant_id=tenant.id, email=email)
        _set_cookie(response, token)
        return {"ok": True, "role": auth.ROLE_OWNER, "tenant": tenant.slug, "email": email}

    client = await find_or_create_client(
        db, tenant_id=tenant.id, google_sub=info["sub"], email=email, name=info["name"]
    )
    token = auth.make_token(
        role=auth.ROLE_PASSENGER, tenant_id=tenant.id, email=email, client_id=client.id
    )
    _set_cookie(response, token)
    return {
        "ok": True,
        "role": auth.ROLE_PASSENGER,
        "client": {"id": client.id, "name": client.name, "email": client.email},
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
    base.update(
        {
            "role": payload.get("role"),
            "email": payload.get("email"),
            "client_id": payload.get("cid"),
            "tenant_id": payload.get("tid"),
        }
    )
    return base


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}
