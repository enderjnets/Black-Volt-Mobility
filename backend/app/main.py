"""FastAPI application entry point for Black Volt Mobility."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.deps import require_admin
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.funnel import router as funnel_router
from app.api.v1.health import router as health_router
from app.api.v1.me import router as me_router
from app.api.v1.payments import router as payments_router
from app.api.v1.rides import router as booking_router
from app.api.v1.social import router as social_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.team import router as team_router
from app.api.v1.tenant import router as tenant_router
from app.api.v1.webhooks import router as webhooks_router
from app.config import get_settings
from app.db.base import dispose_engine, get_session_factory

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger("blackvolt")


async def _seed_admin_users(session, *, tenant_id: int) -> None:
    """Ensure each GOOGLE_ADMIN_EMAILS entry exists as an active admin in
    allowed_users (pinned to the Black Volt tenant) so the owner shows up in the
    Team list. Idempotent; best-effort."""
    from sqlalchemy import select

    from app.models import AllowedUser
    from app.models.allowed_user import ROLE_ADMIN

    for email in settings.google_admin_emails_list:
        row = (
            await session.execute(select(AllowedUser).where(AllowedUser.email == email))
        ).scalar_one_or_none()
        if row is None:
            session.add(
                AllowedUser(
                    email=email, role=ROLE_ADMIN, active=True,
                    tenant_id=tenant_id, added_by="bootstrap",
                )
            )
        else:
            row.role = ROLE_ADMIN
            row.active = True
            if row.tenant_id is None:
                row.tenant_id = tenant_id
    await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s env=%s", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)
    if settings.is_production and not settings.AUTH_ENABLED:
        logger.warning("APP_ENV=production but AUTH_ENABLED=false — dashboard open. Investigate.")
    if settings.is_production and settings.EMAIL_SIMULATED:
        logger.warning("APP_ENV=production but EMAIL_SIMULATED=true — emails off. Investigate.")
    if settings.is_production and not settings.payments_live:
        logger.warning(
            "APP_ENV=production but payments not live — public subscriptions disabled (503)."
        )
    if settings.is_production and settings.SOCIAL_SIMULATED:
        logger.warning(
            "APP_ENV=production but SOCIAL_SIMULATED=true — social publishing simulated."
        )
    try:
        from app.services.tenancy import ensure_seed

        async with get_session_factory()() as session:
            tenant = await ensure_seed(session)
            await _seed_admin_users(session, tenant_id=tenant.id)
    except Exception as e:  # DB not ready yet — get_default_tenant self-heals later
        logger.warning("startup seed skipped: %s", e)
    # In-process scheduler for due social posts (single backend → safe).
    from app.services import scheduler as social_scheduler

    social_scheduler.start()
    yield
    social_scheduler.shutdown()
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
app.include_router(auth_router, prefix="/api/v1")
app.include_router(me_router, prefix="/api/v1")
app.include_router(booking_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(funnel_router, prefix="/api/v1")
app.include_router(social_router, prefix="/api/v1")
app.include_router(tenant_router, prefix="/api/v1")
app.include_router(team_router, prefix="/api/v1", dependencies=[Depends(require_admin)])

# Owner-uploaded brand assets (logo/photo). The directory must exist before the
# mount or StaticFiles raises at import; create it up front (idempotent).
os.makedirs(settings.MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.APP_NAME, "version": settings.APP_VERSION}
