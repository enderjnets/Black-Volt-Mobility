"""Tenant settings API: the dashboard Brand & account editor + the public
profile feed for /d/{slug}.

`/tenant/settings` (GET/PUT) and the logo/photo uploads are staff-only and
tenant-scoped (the tenant comes from the session, never the request body, so a
driver can only edit their own brand). `/tenants/{slug}` is public and returns
only profile-safe fields — no email, no Square token, no internal ids."""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.config import get_settings
from app.db.base import get_db
from app.services import subscriptions, tenancy

router = APIRouter(tags=["tenant"])

_HEX = "0123456789abcdefABCDEF"


def _blank_to_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class TenantSettingsBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tagline: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=2000)
    instagram: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=200)
    vehicle: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    brand_color: str | None = Field(default=None, max_length=9)
    rating: float | None = Field(default=None, ge=0, le=5)
    since_year: int | None = Field(default=None, ge=1950, le=2100)

    @field_validator(
        "tagline", "bio", "instagram", "website", "vehicle", "city", mode="before"
    )
    @classmethod
    def _trim(cls, v):
        return _blank_to_none(v)

    @field_validator("brand_color", mode="before")
    @classmethod
    def _hex(cls, v):
        v = _blank_to_none(v)
        if v is None:
            return None
        s = v if v.startswith("#") else f"#{v}"
        body = s[1:]
        if len(body) not in (3, 6) or any(c not in _HEX for c in body):
            raise ValueError("brand_color must be a hex color like #00E5FF")
        return s.upper()


# Web-displayable image types only; the stored type is derived from the bytes
# (magic number), not the client-sent content-type or filename, so a disguised
# or mislabeled upload is rejected rather than trusted.
def _sniff_image(raw: bytes) -> tuple[str, str] | None:
    """Return (extension, content_type) if the bytes are a supported image."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


async def _save_asset(db: AsyncSession, *, tenant_id: int, kind: str, file: UploadFile) -> str:
    settings = get_settings()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_file")
    if len(raw) > settings.MEDIA_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file_too_large"
        )
    sniffed = _sniff_image(raw)
    if sniffed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_image_type"
        )
    ext, _ctype = sniffed

    rel_dir = os.path.join("tenants", str(tenant_id))
    abs_dir = os.path.join(settings.MEDIA_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    # Versioned filename → the URL changes on every upload (no stale CDN cache).
    fname = f"{kind}-{int(time.time())}.{ext}"
    rel_path = os.path.join(rel_dir, fname)
    abs_path = os.path.join(settings.MEDIA_DIR, rel_path)
    with open(abs_path, "wb") as fh:
        fh.write(raw)

    # Best-effort: drop the previous asset of this kind so the dir doesn't grow.
    t = await tenancy.get_tenant(db, tenant_id)
    old = getattr(t, f"{kind}_path", None) if t else None
    await tenancy.set_tenant_asset(db, tenant_id=tenant_id, kind=kind, path=rel_path)
    if old and old != rel_path:
        try:
            os.remove(os.path.join(settings.MEDIA_DIR, old))
        except OSError:
            pass
    return rel_path


# ─── Dashboard (staff) ──────────────────────────────────────────────────────
@router.get("/tenant/settings")
async def get_tenant_settings(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    out = await tenancy.tenant_settings(db, tenant_id=tenant_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
    return out


@router.put("/tenant/settings")
async def put_tenant_settings(
    body: TenantSettingsBody,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    changes = body.model_dump(exclude_unset=True)
    # name is NOT NULL — never let a blank/None clear it.
    if "name" in changes and not (changes["name"] or "").strip():
        changes.pop("name")
    t = await tenancy.update_tenant(db, tenant_id=tenant_id, changes=changes)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
    return await tenancy.tenant_settings(db, tenant_id=tenant_id)


@router.post("/tenant/logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    await _save_asset(db, tenant_id=tenant_id, kind="logo", file=file)
    return await tenancy.tenant_settings(db, tenant_id=tenant_id)


@router.post("/tenant/photo")
async def upload_photo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    await _save_asset(db, tenant_id=tenant_id, kind="photo", file=file)
    return await tenancy.tenant_settings(db, tenant_id=tenant_id)


# ─── Public profile ─────────────────────────────────────────────────────────
@router.get("/tenants/{slug}")
async def get_public_profile(slug: str, db: AsyncSession = Depends(get_db)):
    t = await tenancy.get_tenant_by_slug(db, slug)
    # An unpaid tenant's profile is a plain 404 (never 402): billing state must
    # not be revealed publicly.
    if t is None or not await subscriptions.tenant_has_entitlements(db, tenant_id=t.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return await tenancy.public_profile(db, slug=slug)
