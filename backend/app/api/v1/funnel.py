"""Driver sales-funnel API (the "My Stats" tab). Staff-only, tenant-scoped.

GET  /stats/funnel            → full summary (funnel rates, streak, projection)
POST /stats/funnel/log        → upsert one day's logged counts
GET  /stats/funnel/goal       → current goal
PUT  /stats/funnel/goal       → set goal
POST /stats/funnel/project    → goal calculator (target → required activity)
"""
from __future__ import annotations

import datetime as dt
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.db.base import get_db
from app.services import funnel

router = APIRouter(tags=["funnel"])


class FunnelLogBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    # JSON key is "date"; the Python attr is log_date to avoid shadowing the type.
    log_date: dt.date | None = Field(default=None, alias="date")
    conversations: int = Field(default=0, ge=0, le=10000)
    pitches: int = Field(default=0, ge=0, le=10000)
    contacts: int = Field(default=0, ge=0, le=10000)
    notes: str | None = Field(default=None, max_length=2000)


class GoalBody(BaseModel):
    target_weekly_revenue: float | None = Field(default=None, ge=0, le=1_000_000)
    target_monthly_clients: int | None = Field(default=None, ge=0, le=100_000)
    working_days_per_week: int = Field(default=5, ge=1, le=7)


class ProjectBody(BaseModel):
    period: str = "week"  # week | month | year
    target_revenue: float | None = Field(default=None, ge=0, le=100_000_000)
    target_clients: float | None = Field(default=None, ge=0, le=1_000_000)


@router.get("/stats/funnel")
async def get_funnel(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await funnel.summary(db, tenant_id=tenant_id, days=days)


@router.post("/stats/funnel/log")
async def post_funnel_log(
    body: FunnelLogBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    log_date = body.log_date or datetime.now(UTC).date()
    row = await funnel.upsert_log(
        db,
        tenant_id=tenant_id,
        log_date=log_date,
        conversations=body.conversations,
        pitches=body.pitches,
        contacts=body.contacts,
        notes=body.notes,
    )
    return funnel._log_out(row)


@router.get("/stats/funnel/goal")
async def get_funnel_goal(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await funnel.get_goal(db, tenant_id=tenant_id)


@router.put("/stats/funnel/goal")
async def put_funnel_goal(
    body: GoalBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await funnel.set_goal(
        db,
        tenant_id=tenant_id,
        target_weekly_revenue=body.target_weekly_revenue,
        target_monthly_clients=body.target_monthly_clients,
        working_days_per_week=body.working_days_per_week,
    )


@router.post("/stats/funnel/project")
async def post_funnel_project(
    body: ProjectBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await funnel.project(
        db,
        tenant_id=tenant_id,
        period=body.period,
        target_revenue=body.target_revenue,
        target_clients=body.target_clients,
    )
