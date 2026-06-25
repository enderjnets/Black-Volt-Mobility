"""Passenger self-service profile API.

Powers the onboarding gate on /book and the account page: the signed-in
passenger reads and completes their own profile. Scoping is by the session's
client_id (`cid`) — never a value from the request body — so a passenger can
only ever touch their own record.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_passenger
from app.db.base import get_db
from app.models import Client
from app.services import profile as profile_svc
from app.services.phone import InvalidPhoneError, normalize_phone

router = APIRouter(tags=["me"])


class ProfilePatch(BaseModel):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    home_address: str | None = Field(default=None, max_length=400)
    sms_consent: bool | None = None
    email_consent: bool | None = None
    lang: str | None = Field(default=None, max_length=40)


async def _load_own(db: AsyncSession, payload: dict) -> Client:
    """Load the session's own Client (by the trusted token cid).

    Scoped to the token's tenant as defense-in-depth — `cid` alone is already
    authoritative (it's server-minted and HMAC-signed), the tenant filter just
    keeps this consistent with the rest of the multi-tenant data access."""
    cid = int(payload["cid"])
    stmt = select(Client).where(Client.id == cid)
    tid = payload.get("tid")
    if tid is not None:
        stmt = stmt.where(Client.tenant_id == int(tid))
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="client_not_found")
    return row


def _clean(value: str | None) -> str | None:
    """Trim, and treat blank as cleared (None)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


@router.get("/me/profile")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_passenger),
):
    return profile_svc.serialize(await _load_own(db, payload))


@router.patch("/me/profile")
async def patch_profile(
    body: ProfilePatch,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_passenger),
):
    row = await _load_own(db, payload)
    changes = body.model_dump(exclude_unset=True)

    if "phone" in changes:
        cleaned = _clean(changes["phone"])
        if cleaned is None:
            row.phone = None
        else:
            try:
                row.phone = normalize_phone(cleaned)
            except InvalidPhoneError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"invalid_phone:{e}",
                ) from e

    for field in ("first_name", "last_name", "home_address"):
        if field in changes:
            setattr(row, field, _clean(changes[field]))

    if "sms_consent" in changes:
        row.sms_consent = bool(changes["sms_consent"])

    if "email_consent" in changes:
        row.email_consent = bool(changes["email_consent"])

    if "lang" in changes:
        row.lang = profile_svc.normalize_lang(changes["lang"])

    if "first_name" in changes or "last_name" in changes:
        row.name = f"{row.first_name or ''} {row.last_name or ''}".strip() or None

    await db.commit()
    await db.refresh(row)
    return profile_svc.serialize(row)
