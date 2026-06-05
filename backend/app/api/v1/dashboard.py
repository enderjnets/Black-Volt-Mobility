"""Driver dashboard API: KPI stats + client CRM. Staff-only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.api.v1.rides import _normalize_lang
from app.db.base import get_db
from app.services import dashboard

router = APIRouter(tags=["dashboard"])


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    lang: str | None = None

    _norm_lang = field_validator("lang", mode="before")(_normalize_lang)


@router.get("/dashboard/stats")
async def dashboard_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await dashboard.stats(db, tenant_id=tenant_id)


@router.get("/clients")
async def list_clients(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return {"clients": await dashboard.list_clients(db, tenant_id=tenant_id)}


@router.get("/clients/{client_id}")
async def get_client(
    client_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    detail = await dashboard.client_detail(db, tenant_id=tenant_id, client_id=client_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="client_not_found")
    return detail


@router.patch("/clients/{client_id}")
async def patch_client(
    client_id: int,
    body: ClientPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    c = await dashboard.update_client(
        db, tenant_id=tenant_id, client_id=client_id, changes=body.model_dump(exclude_unset=True)
    )
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="client_not_found")
    return await dashboard.client_detail(db, tenant_id=tenant_id, client_id=client_id)
