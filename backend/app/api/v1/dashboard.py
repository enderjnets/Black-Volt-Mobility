"""Driver dashboard API: KPI stats + client CRM. Staff-only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.db.base import get_db
from app.services import dashboard

router = APIRouter(tags=["dashboard"])


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
