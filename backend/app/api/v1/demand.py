"""'Where to wait' API (staff-only, tenant-scoped).

POST /demand/import          → upload the Uber data export ZIP
GET  /demand/import/status   → last import summary
POST /demand/log             → one-tap shift/offer event            (Task 6)
GET  /demand/log/today       → today's events + current state       (Task 6)
GET  /demand/week            → 7×24 planner grid + top blocks       (Task 9)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.db.base import get_db
from app.services import uber_import

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
        return await uber_import.import_export(db, tenant_id=tenant_id, data=data)
    except uber_import.ImportError_ as e:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if e.code == "too_large" else 400
        raise HTTPException(status_code=code, detail=e.code) from e


@router.get("/demand/import/status")
async def get_import_status(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    last = await uber_import.last_import(db, tenant_id=tenant_id)
    return last if last is not None else {"never": True}
