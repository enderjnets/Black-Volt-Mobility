"""Shared pytest fixtures.

The suite runs against a long-lived dev database, so rides created by earlier
runs accumulate. List-endpoint tests page at a fixed limit, so once enough rides
pile up a freshly-created ride sorts past the page and the assertion flakes. We
reset the ride/payment tables once at session start (never on a production DB) so
every run starts clean and list tests are deterministic regardless of history.

A one-shot asyncpg connection is used (not the app's cached engine) so the reset
runs in its own short-lived event loop and never collides with the per-test loop
pytest-asyncio manages.
"""
import asyncio
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _reset_ride_data():
    from app.config import get_settings

    settings = get_settings()
    # Hard safety: only ever reset inside the test harness. The test modules set
    # DASHBOARD_PASSWORD="test-pw" at import; a real deployment never does. This
    # guards against wiping a live DB even when APP_ENV is "development" (the ROG
    # backend runs that env), where an is_production check alone would not.
    if settings.is_production or os.environ.get("DASHBOARD_PASSWORD") != "test-pw":
        yield
        return

    async def _truncate():
        import asyncpg

        dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            # Funnel/platform/goal rows also accumulate across runs and shift the
            # My Stats + coach aggregates (e.g. which stage is the bottleneck), so
            # reset them too for deterministic funnel/coach tests.
            await conn.execute(
                "TRUNCATE rides, payments, driver_funnel_logs, platform_stats, "
                "driver_goals, social_posts, social_interactions, social_accounts, "
                "document_consents, reviews, review_invites, events, "
                "event_suggestions, clients "
                "RESTART IDENTITY CASCADE"
            )
        finally:
            await conn.close()

    asyncio.run(_truncate())
    yield
