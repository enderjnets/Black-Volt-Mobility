"""Flights API (staff-only, tenant-scoped).

GET /flights/upcoming → the driver's own flights in the next window, ordered
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.db.base import get_db
from app.services import flights

router = APIRouter(tags=["flights"])


@router.get("/flights/upcoming")
async def get_upcoming(
    hours: int = Query(default=flights.WINDOW_HOURS, ge=1, le=336),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await flights.upcoming(db, tenant_id=tenant_id, hours=hours)
