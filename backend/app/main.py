"""FastAPI application entry point for Black Volt Mobility."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.config import get_settings
from app.db.base import dispose_engine

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger("blackvolt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s env=%s", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)
    if settings.is_production and not settings.AUTH_ENABLED:
        logger.warning("APP_ENV=production but AUTH_ENABLED=false — dashboard open. Investigate.")
    yield
    await dispose_engine()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.APP_NAME, "version": settings.APP_VERSION}
