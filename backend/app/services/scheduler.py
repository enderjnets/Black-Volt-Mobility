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


async def _review_reminders_job() -> None:
    """Email a review request to riders whose ride completed ~N hours ago (per tenant)."""
    try:
        from app.db.base import get_session_factory
        from app.services import reviews

        async with get_session_factory()() as db:
            n = await reviews.send_due_reminders(db)
            if n:
                logger.info("review reminders sent: %d", n)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("review_reminders job failed: %s", e)


async def _pickup_reminders_job() -> None:
    """Push a reminder to passengers whose confirmed ride departs soon (all tenants)."""
    try:
        from app.db.base import get_session_factory
        from app.services import push

        async with get_session_factory()() as db:
            n = await push.send_due_pickup_reminders(db)
            if n:
                logger.info("pickup reminders pushed: %d", n)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("pickup_reminders job failed: %s", e)


async def _events_scan_job() -> None:
    """Daily 06:00 Denver: pull big upcoming events into suggestions; archive past events."""
    try:
        from app.db.base import get_session_factory
        from app.services import events, events_scan

        async with get_session_factory()() as db:
            out = await events_scan.run_scan(db)
            n = await events.archive_past_events(db)
            logger.info("events scan: %s, archived=%d", out, n)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("events_scan job failed: %s", e)


async def _blog_keywords_job() -> None:
    """Daily 05:00 Denver: discover + score SEO keywords, promote the best to planned."""
    try:
        from app.db.base import get_session_factory
        from app.services import blog_keywords
        from app.services.tenancy import owner_tenant_id

        async with get_session_factory()() as db:
            out = await blog_keywords.run_daily(db, tenant_id=await owner_tenant_id(db))
            logger.info("blog keyword discovery: %s", out)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("blog_keywords job failed: %s", e)


async def _blog_writer_job() -> None:
    """Daily 07:00 Denver: write one bilingual article from the top planned keyword."""
    try:
        from app.db.base import get_session_factory
        from app.services import blog_writer
        from app.services.tenancy import owner_tenant_id

        async with get_session_factory()() as db:
            out = await blog_writer.run_daily(db, tenant_id=await owner_tenant_id(db))
            logger.info("blog writer: %s", out)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("blog_writer job failed: %s", e)


async def _blog_publish_job() -> None:
    """Every 15 min: publish scheduled articles whose 24h edit window elapsed + auto-share."""
    try:
        from app.db.base import get_session_factory
        from app.services import blog_publish
        from app.services.tenancy import owner_tenant_id

        async with get_session_factory()() as db:
            out = await blog_publish.publish_due(db, tenant_id=await owner_tenant_id(db))
            if out.get("published"):
                logger.info("blog publish: %s", out)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("blog_publish job failed: %s", e)


async def _blog_speed_job() -> None:
    """Daily 03:00 Denver: measure the public pages (Speed tab).

    Deliberately not gated by the blog's `paused` flag: pausing stops producing content, it
    does not stop the site from needing to be fast.
    """
    try:
        from app.db.base import get_session_factory
        from app.services import site_speed
        from app.services.tenancy import owner_tenant_id

        async with get_session_factory()() as db:
            out = await site_speed.run_daily(db, tenant_id=await owner_tenant_id(db))
            logger.info("blog speed: %s", out)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("blog_speed job failed: %s", e)


async def _blog_gsc_job() -> None:
    """Daily 04:00 Denver: Google Search Console snapshot (Analytics tab). No-op until connected."""
    try:
        from app.db.base import get_session_factory
        from app.services import gsc
        from app.services.tenancy import owner_tenant_id

        async with get_session_factory()() as db:
            tid = await owner_tenant_id(db)
            logger.info("blog gsc: %s", await gsc.run_daily(db, tenant_id=tid))
            logger.info("blog indexing: %s", await gsc.run_indexing(db, tenant_id=tid))
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("blog_gsc job failed: %s", e)


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
        # Auto review-request reminders: email riders ~N hours after their ride completes.
        sched.add_job(
            _review_reminders_job, "interval", minutes=15, id="review_reminders",
            max_instances=1, coalesce=True,
        )
        # Passenger pickup-reminder pushes (PWA). Interval keeps the lead-time tight.
        sched.add_job(
            _pickup_reminders_job, "interval", minutes=15, id="pickup_reminders",
            max_instances=1, coalesce=True,
        )
        # Daily featured-events scan + archive (Denver local time). Gated so a
        # deployment without event API keys simply never schedules it.
        if get_settings().EVENTS_SCAN_ENABLED:
            sched.add_job(
                _events_scan_job,
                CronTrigger(hour=6, minute=0, timezone="America/Denver"),
                id="events_daily_scan", max_instances=1, coalesce=True,
            )
        if get_settings().BLOG_AUTOPILOT_ENABLED:
            sched.add_job(
                _blog_keywords_job,
                CronTrigger(hour=5, minute=0, timezone="America/Denver"),
                id="blog_daily_keywords", max_instances=1, coalesce=True,
            )
            sched.add_job(
                _blog_writer_job,
                CronTrigger(hour=7, minute=0, timezone="America/Denver"),
                id="blog_daily_writer", max_instances=1, coalesce=True,
            )
            sched.add_job(
                _blog_publish_job, "interval", minutes=15,
                id="blog_publish_due", max_instances=1, coalesce=True,
            )
            sched.add_job(
                _blog_speed_job,
                CronTrigger(hour=3, minute=0, timezone="America/Denver"),
                id="blog_daily_speed", max_instances=1, coalesce=True,
            )
            sched.add_job(
                _blog_gsc_job,
                CronTrigger(hour=4, minute=0, timezone="America/Denver"),
                id="blog_daily_gsc", max_instances=1, coalesce=True,
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
