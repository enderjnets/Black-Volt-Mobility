"""In-process background scheduler for the social module.

A single `AsyncIOScheduler` runs inside the FastAPI process (started/stopped from
the app lifespan). For the small single-backend deployment this is enough — there
is exactly one instance, so jobs never double-fire. If the backend is ever scaled
horizontally, move these to a dedicated worker with a shared lock (documented
caveat).

Stage 1 has one meaningful job: publish posts whose scheduled time has arrived.
Comment polling / engagement sync are no-ops while simulated and become live in
later stages. Every job runs in its own DB session and swallows its own errors so
a transient failure never kills the scheduler.
"""
from __future__ import annotations

import logging

from app.config import get_settings

logger = logging.getLogger("blackvolt.social.scheduler")

_scheduler = None  # the AsyncIOScheduler, or None if unavailable/not started


async def _publish_due_job() -> None:
    """Publish any scheduled post whose time has come (all tenants)."""
    try:
        from app.db.base import get_session_factory
        from app.services import social

        async with get_session_factory()() as db:
            await social.publish_due(db)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("publish_due job failed: %s", e)


async def _daily_generate_job() -> None:
    """Generate + render one MrBeast-style post per tenant per day (09:00 Denver)."""
    try:
        from app.db.base import get_session_factory
        from app.services import social

        async with get_session_factory()() as db:
            await social.generate_daily_for_all_tenants(db)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("daily_generate job failed: %s", e)


def start() -> None:
    """Start the scheduler. Best-effort: a missing APScheduler or any startup
    error degrades to 'no background publishing' rather than breaking the app."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except Exception as e:
        logger.warning("APScheduler unavailable — scheduled publishing disabled: %s", e)
        return
    try:
        sched = AsyncIOScheduler(timezone="UTC")
        sched.add_job(
            _publish_due_job, "interval", minutes=2, id="social_publish_due",
            max_instances=1, coalesce=True,
        )
        # One MrBeast-style auto-post per tenant each morning (Denver local time).
        from apscheduler.triggers.cron import CronTrigger

        sched.add_job(
            _daily_generate_job,
            CronTrigger(hour=9, minute=0, timezone="America/Denver"),
            id="social_daily_generate", max_instances=1, coalesce=True,
        )
        sched.start()
        _scheduler = sched
        logger.info("social scheduler started (simulated=%s)", get_settings().SOCIAL_SIMULATED)
    except Exception as e:
        logger.warning("failed to start social scheduler: %s", e)


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception as e:
            logger.warning("scheduler shutdown error: %s", e)
        _scheduler = None
