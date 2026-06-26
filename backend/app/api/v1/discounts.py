"""Discount codes and campaigns API.

Staff routes (require_staff): CRUD for their own tenant's codes.
Passenger route (require_auth): validate a code before booking.
Admin routes (require_admin): campaign creation + driver list.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    require_admin,
    require_auth,
    require_staff,
    resolve_tenant_id,
    session_is_admin,
)
from app.db.base import get_db
from app.models.allowed_user import ROLE_DRIVER, AllowedUser
from app.services.discounts import (
    DiscountError,
    create_campaign,
    create_code,
    delete_code,
    list_codes,
    set_active,
    validate_code,
)

router = APIRouter(prefix="/discounts", tags=["discounts"])


# ─── Schemas ─────────────────────────────────────────────────────────────────


class CodeIn(BaseModel):
    code: str = ""
    discount_pct: float
    max_uses: int = Field(ge=1)
    expires_at: dt.datetime


class CodeOut(BaseModel):
    id: int
    tenant_id: int
    code: str
    discount_pct: float
    max_uses: int
    used_count: int
    expires_at: dt.datetime
    active: bool
    created_by_email: str
    campaign_id: int | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class ActivePatch(BaseModel):
    active: bool


class ValidateIn(BaseModel):
    code: str


class ValidateOut(BaseModel):
    valid: bool
    discount_pct: float


class CampaignIn(BaseModel):
    name: str
    discount_pct: float
    max_uses: int = Field(ge=1)
    expires_at: dt.datetime
    driver_tenant_ids: list[int]


class CampaignOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    discount_pct: float
    max_uses: int
    expires_at: dt.datetime
    created_by_email: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class DriverOut(BaseModel):
    tenant_id: int
    email: str


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.get("", response_model=list[CodeOut])
async def list_discount_codes(
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> list[CodeOut]:
    tenant_id = await resolve_tenant_id(db, payload)
    rows = await list_codes(db, tenant_id)
    return [CodeOut.model_validate(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CodeOut)
async def create_discount_code(
    body: CodeIn,
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> CodeOut:
    tenant_id = await resolve_tenant_id(db, payload)
    is_admin = await session_is_admin(db, payload)
    email = (payload.get("email") or "").lower().strip()
    try:
        row = await create_code(
            db,
            tenant_id=tenant_id,
            is_admin=is_admin,
            code=body.code,
            discount_pct=body.discount_pct,
            max_uses=body.max_uses,
            expires_at=body.expires_at,
            created_by_email=email,
        )
    except DiscountError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.reason
        ) from e
    return CodeOut.model_validate(row)


@router.patch("/{code_id}", response_model=CodeOut)
async def patch_discount_code(
    code_id: int,
    body: ActivePatch,
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> CodeOut:
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        row = await set_active(db, tenant_id, code_id, body.active)
    except DiscountError as e:
        if e.reason == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.reason) from e
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.reason
        ) from e
    return CodeOut.model_validate(row)


@router.delete("/{code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discount_code(
    code_id: int,
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        await delete_code(db, tenant_id, code_id)
    except DiscountError as e:
        if e.reason == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.reason) from e
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.reason
        ) from e


@router.post("/validate", response_model=ValidateOut)
async def validate_discount_code(
    body: ValidateIn,
    payload: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ValidateOut:
    try:
        row = await validate_code(db, body.code)
    except DiscountError as e:
        if e.reason == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.reason) from e
        if e.reason in ("expired", "exhausted", "inactive"):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=e.reason) from e
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.reason
        ) from e
    return ValidateOut(valid=True, discount_pct=row.discount_pct)


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_discount_campaign(
    body: CampaignIn,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    email = (payload.get("email") or "").lower().strip()
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        camp, codes = await create_campaign(
            db,
            name=body.name,
            discount_pct=body.discount_pct,
            max_uses=body.max_uses,
            expires_at=body.expires_at,
            created_by_email=email,
            created_by_tenant_id=tenant_id,
            driver_tenant_ids=body.driver_tenant_ids,
        )
    except DiscountError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.reason
        ) from e
    return {
        "campaign": CampaignOut.model_validate(camp).model_dump(),
        "codes": [CodeOut.model_validate(c).model_dump() for c in codes],
    }


@router.get("/drivers", response_model=list[DriverOut])
async def list_drivers(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DriverOut]:
    rows = (
        await db.execute(
            select(AllowedUser).where(
                AllowedUser.role == ROLE_DRIVER,
                AllowedUser.active.is_(True),
                AllowedUser.tenant_id.isnot(None),
            )
        )
    ).scalars().all()
    return [DriverOut(tenant_id=r.tenant_id, email=r.email) for r in rows]
