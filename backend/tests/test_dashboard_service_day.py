"""Dashboard KPIs bucket rides by the DRIVER'S day, not the server's UTC day.

Denver is UTC-6/-7, so a 19:45 pickup is 01:45 UTC the next day. Bucketing on UTC put
that ride on tomorrow's "Rides today" and moved its bar one column right on the weekly
chart — the owner saw yesterday evening's ride reported as today's revenue.

Runs against the isolated blackvolt_test DB, never prod.
"""
import asyncio
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["CALENDAR_TIMEZONE"] = "America/Denver"


from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Ride, RideStatus  # noqa: E402
from app.services import dashboard  # noqa: E402
from tests.test_ride_messages_api import _seed_tenant_client, _session_factory  # noqa: E402

DENVER = ZoneInfo("America/Denver")


def _ride_at(tenant_id: int, local: datetime, *, fare: float, tip: float | None = None) -> int:
    """Create a COMPLETED ride at a Denver wall-clock time."""

    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                r = Ride(
                    tenant_id=tenant_id,
                    status=RideStatus.COMPLETED,
                    pickup_text="A",
                    dropoff_text="B",
                    scheduled_at=local.replace(tzinfo=DENVER).astimezone(UTC),
                    fare_total=fare,
                    tip=tip,
                    lang="en",
                )
                db.add(r)
                await db.commit()
                await db.refresh(r)
                return r.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _stats(tenant_id: int) -> dict:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                return await dashboard.stats(db, tenant_id=tenant_id)
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _week(tenant_id: int, monday) -> dict:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                return await dashboard.week_earnings(db, tenant_id=tenant_id, monday=monday)
        finally:
            await eng.dispose()

    return asyncio.run(go())


def test_service_day_uses_the_drivers_timezone_not_utc():
    assert dashboard.service_tz() == "America/Denver"
    assert dashboard.today_local() == datetime.now(DENVER).date()


def test_evening_ride_counts_today_not_tomorrow():
    """THE regression: 19:45 in Denver is already 01:45 UTC tomorrow. It must still be
    reported as today's ride and today's revenue."""
    _cid, tenant = _seed_tenant_client("tzday")
    today = datetime.now(DENVER).date()
    evening = datetime.combine(today, datetime.min.time()) + timedelta(hours=19, minutes=45)
    _ride_at(tenant, evening, fare=145, tip=10)

    s = _stats(tenant)
    assert s["today"]["rides"] == 1
    assert s["today"]["revenue"] == 155.0  # fare + tip


def test_a_ride_after_midnight_utc_yesterday_is_not_todays():
    """Mirror case: 20:00 Denver YESTERDAY is 02:00 UTC today. Under UTC bucketing it
    leaked into today's numbers — that is exactly what the owner was seeing."""
    _cid, tenant = _seed_tenant_client("tzyest")
    yesterday = datetime.now(DENVER).date() - timedelta(days=1)
    late = datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=20)
    _ride_at(tenant, late, fare=145, tip=10)

    s = _stats(tenant)
    assert s["today"]["rides"] == 0
    assert s["today"]["revenue"] == 0.0


def test_weekly_chart_puts_an_evening_ride_on_its_own_day():
    """The bar must sit under the day the ride was actually driven."""
    _cid, tenant = _seed_tenant_client("tzweek")
    today = datetime.now(DENVER).date()
    evening = datetime.combine(today, datetime.min.time()) + timedelta(hours=21, minutes=20)
    _ride_at(tenant, evening, fare=100)

    wk = _week(tenant, dashboard.monday_of(today))

    by_date = {d["date"]: d["revenue"] for d in wk["days"]}
    assert by_date[str(today)] == 100.0
    assert wk["total"] == 100.0
    tomorrow = str(today + timedelta(days=1))
    if tomorrow in by_date:  # only when today isn't Sunday
        assert by_date[tomorrow] == 0.0


def test_week_total_matches_the_sum_of_its_days():
    """The card's total and the bars are the same data — they can't disagree."""
    _cid, tenant = _seed_tenant_client("tzsum")
    today = datetime.now(DENVER).date()
    monday = dashboard.monday_of(today)
    for i in range(3):
        day = monday + timedelta(days=i)
        if day > today:
            break
        _ride_at(
            tenant,
            datetime.combine(day, datetime.min.time()) + timedelta(hours=22),
            fare=50,
            tip=5,
        )

    wk = _week(tenant, monday)

    assert wk["total"] == round(sum(d["revenue"] for d in wk["days"]), 2)
    assert wk["total"] > 0, "late-evening rides must not fall outside the week"


def test_tips_are_included_in_the_week():
    """The owner suspected tips were missing from 'This week'. They are not — this
    pins that behaviour so it stays true."""
    _cid, tenant = _seed_tenant_client("tztip")
    today = datetime.now(DENVER).date()
    noon = datetime.combine(today, datetime.min.time()) + timedelta(hours=12)
    _ride_at(tenant, noon, fare=115, tip=20)

    wk = _week(tenant, dashboard.monday_of(today))

    assert wk["total"] == 135.0
