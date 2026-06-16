"""Driver sales-funnel API (the "My Stats" tab). Staff-only, tenant-scoped.

GET  /stats/funnel            → full summary (funnel rates, streak, projection)
POST /stats/funnel/log        → upsert one day's logged counts
GET  /stats/funnel/goal       → current goal
PUT  /stats/funnel/goal       → set goal
POST /stats/funnel/project    → goal calculator (target → required activity)
POST /stats/platform/extract  → read an Uber/Lyft/Co-op screenshot (AI vision)
GET  /stats/platform          → platform-income summary + vs-private comparison
POST /stats/platform          → save a confirmed platform-stats record
DELETE /stats/platform/{id}   → delete a platform-stats record
"""
from __future__ import annotations

import datetime as dt
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.config import get_settings
from app.db.base import get_db
from app.services import coach, funnel, platform_stats, subscriptions

router = APIRouter(tags=["funnel"])

# Accepted screenshot types / size (mirrors the Smart reservation upload).
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


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


@router.get("/stats/coach")
async def get_coach(
    request: Request,
    lang: str = Query(default="en"),
    refresh: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """One deterministic, AI-phrased coaching nudge for the My Stats tab."""
    tenant_id = await resolve_tenant_id(db, payload)
    return await coach.recommend(db, tenant_id=tenant_id, locale=lang, refresh=refresh)


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


# ── Platform stats (Uber/Lyft/Co-op screenshot import) ───────────────────────
class PlatformStatBody(BaseModel):
    platform: str = Field(default="other", max_length=20)
    period_label: str | None = Field(default=None, max_length=80)
    period_start: str | None = Field(default=None, max_length=20)
    period_end: str | None = Field(default=None, max_length=20)
    trips: int | None = Field(default=None, ge=0, le=100000)
    earnings: float | None = Field(default=None, ge=0, le=10_000_000)
    online_hours: float | None = Field(default=None, ge=0, le=10000)
    currency: str | None = Field(default=None, max_length=3)


@router.post("/stats/platform/extract")
async def post_platform_extract(
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Read 1..N screenshots of an Uber/Lyft/Co-op earnings summary and return the
    parsed fields for the driver to review before saving. Best-effort (a vision
    failure returns all-null). Gated behind an active subscription (AI feature)."""
    tenant_id = await resolve_tenant_id(db, payload)
    if not await subscriptions.tenant_has_entitlements(db, tenant_id=tenant_id):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="subscription_required"
        )
    settings = get_settings()
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_files")
    if len(files) > settings.SMART_MAX_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"too_many_images_max_{settings.SMART_MAX_IMAGES}",
        )
    images: list[tuple[str, bytes]] = []
    for f in files:
        media_type = (f.content_type or "").split(";")[0].strip().lower()
        if media_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_image_type"
            )
        raw = await f.read()
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_image")
        if len(raw) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="image_too_large"
            )
        images.append((media_type, raw))
    fields = await platform_stats.extract_platform_stats(images)
    return {"fields": fields, "simulated": not settings.smart_live, "image_count": len(images)}


@router.get("/stats/platform")
async def get_platform(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await platform_stats.summary(db, tenant_id=tenant_id, days=days)


@router.post("/stats/platform", status_code=status.HTTP_201_CREATED)
async def post_platform(
    body: PlatformStatBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await platform_stats.save_stat(
        db,
        tenant_id=tenant_id,
        platform=body.platform,
        period_label=body.period_label,
        period_start=body.period_start,
        period_end=body.period_end,
        trips=body.trips,
        earnings=body.earnings,
        online_hours=body.online_hours,
        currency=body.currency,
    )


@router.delete("/stats/platform/{stat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(
    stat_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    ok = await platform_stats.delete_stat(db, tenant_id=tenant_id, stat_id=stat_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stat_not_found")
    return None
