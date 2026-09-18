"""'Where to wait' API (staff-only, tenant-scoped).

POST /demand/import          → upload the Uber data export ZIP
GET  /demand/import/status   → last import summary
POST /demand/log             → one-tap shift/offer event            (Task 6)
GET  /demand/log/today       → today's events + current state       (Task 6)
GET  /demand/week            → 7×24 planner grid + top blocks       (Task 9)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.db.base import get_db
from app.services import demand, shift_log, uber_import

logger = logging.getLogger("blackvolt.demand")
router = APIRouter(tags=["demand"])


@router.post("/demand/import", status_code=status.HTTP_201_CREATED)
async def post_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    data = await file.read(uber_import.MAX_ZIP_BYTES + 1)
    if len(data) > uber_import.MAX_ZIP_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="too_large"
        )
    try:
        out = await uber_import.import_export(db, tenant_id=tenant_id, data=data)
    except uber_import.ImportError_ as e:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if e.code == "too_large" else 400
        raise HTTPException(status_code=code, detail=e.code) from e
    # Recompute here rather than leaving it to the hourly job. Uploading an export and
    # finding last month's week still on screen reads as a failed upload; it took a
    # hand-run recompute to notice on the day this shipped. Best-effort on purpose: the
    # rows are already committed, the job would pick them up anyway, and an import that
    # succeeded must not report failure because the arithmetic after it did.
    try:
        await demand.recompute_week(db, tenant_id=tenant_id)
    except Exception as e:  # noqa: BLE001 - the upload itself already succeeded
        logger.warning("post-import recompute failed for tenant %s: %s", tenant_id, e)
    return out


@router.get("/demand/import/status")
async def get_import_status(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    last = await uber_import.last_import(db, tenant_id=tenant_id)
    return last if last is not None else {"never": True}


class LogBody(BaseModel):
    client_event_id: str = Field(min_length=1, max_length=64)
    kind: str
    at: datetime | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    product: str | None = None
    accepted: bool | None = None
    fare: float | None = Field(default=None, ge=0, le=10000)
    dest_text: str | None = Field(default=None, max_length=200)


@router.post("/demand/log", status_code=status.HTTP_201_CREATED)
async def post_log(
    body: LogBody,
    response: Response,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        event, created = await shift_log.log_event(
            db,
            tenant_id=tenant_id,
            client_event_id=body.client_event_id,
            kind=body.kind,
            at=body.at,
            lat=body.lat,
            lng=body.lng,
            product=body.product,
            accepted=body.accepted,
            fare=body.fare,
            dest_text=body.dest_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    if not created:
        response.status_code = status.HTTP_200_OK
    return event


@router.get("/demand/log/today")
async def get_log_today(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    now = None
    if date:
        y, m, d = (int(x) for x in date.split("-"))
        now = datetime(y, m, d, 12, 0, tzinfo=shift_log.DENVER).astimezone(UTC)
    return await shift_log.today(db, tenant_id=tenant_id, now=now)


@router.get("/demand/week")
async def get_week(
    response: Response,
    zone: str | None = Query(default=None, max_length=40),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    body = await demand.week_payload(db, tenant_id=tenant_id, zone=zone)
    if body is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_zone")
    response.headers["ETag"] = demand.etag_for(body)
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=900"
    return body
