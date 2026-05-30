"""Health check endpoint — no auth, used by Docker healthcheck + monitoring."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    settings = get_settings()
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "db": db_ok,
    }
