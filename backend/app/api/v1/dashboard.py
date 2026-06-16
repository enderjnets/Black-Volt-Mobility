"""Driver dashboard API: KPI stats + client CRM. Staff-only."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
    home_address: str | None = Field(default=None, max_length=400)

    _norm_lang = field_validator("lang", mode="before")(_normalize_lang)


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    lang: str | None = None
    home_address: str | None = Field(default=None, max_length=400)

    _norm_lang = field_validator("lang", mode="before")(_normalize_lang)


@router.get("/dashboard/stats")
async def dashboard_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await dashboard.stats(db, tenant_id=tenant_id)


@router.get("/dashboard/week")
async def dashboard_week(
    request: Request,
    offset: int = Query(default=0, ge=-260, le=0),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Daily earned revenue for a single Mon→Sun week, for the "This week" chart's
    week navigator. `offset` 0 = current week, negative = past weeks; future weeks
    are not allowed (`le=0`). Bounded to ~5 years back (`ge=-260`)."""
    tenant_id = await resolve_tenant_id(db, payload)
    monday = dashboard.monday_of(datetime.now(UTC).date()) + timedelta(weeks=offset)
    week = await dashboard.week_earnings(db, tenant_id=tenant_id, monday=monday)
    week["offset"] = offset
    return week


@router.get("/dashboard/weeks")
async def dashboard_weeks(
    request: Request,
    count: int = Query(default=12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Earned-revenue totals for the last `count` weeks (for the week-picker
    dropdown). Returns [{offset, start, end, total}], offset 0 = current week."""
    tenant_id = await resolve_tenant_id(db, payload)
    return await dashboard.weeks_summary(db, tenant_id=tenant_id, count=count)


@router.get("/clients")
async def list_clients(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return {"clients": await dashboard.list_clients(db, tenant_id=tenant_id)}


# NOTE: must be declared BEFORE GET /clients/{client_id} — "search" would fail the
# int path-param parse and never reach a route declared after it.
@router.get("/clients/search")
async def search_clients(
    request: Request,
    q: str = Query(default="", max_length=120),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return {"clients": await dashboard.search_clients(db, tenant_id=tenant_id, q=q)}


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    c = await dashboard.create_client(
        db,
        tenant_id=tenant_id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        lang=body.lang,
        home_address=body.home_address,
    )
    return await dashboard.client_detail(db, tenant_id=tenant_id, client_id=c.id)


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    ok = await dashboard.delete_client(db, tenant_id=tenant_id, client_id=client_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="client_not_found")


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
