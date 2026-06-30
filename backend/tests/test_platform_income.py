"""Platform-income correctness: the platform-vs-private comparison, multi-platform
aggregation, window attribution and tenant isolation that the My Stats panel relies on.

Service-level + deterministic: each test uses its own isolated tenant (tenants are not
truncated between runs) and asserts exact numbers, so results don't depend on other data.
"""

import asyncio
import datetime as dt
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models import Ride, RideStatus, Tenant  # noqa: E402
from app.services import platform_stats  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def _sf():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


async def _mk_tenant(slug: str) -> int:
    eng, sf = _sf()
    try:
        async with sf() as db:
            t = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
            if t is None:
                t = Tenant(slug=slug, name=slug.replace("-", " ").title())
                db.add(t)
                await db.commit()
                await db.refresh(t)
            return t.id
    finally:
        await eng.dispose()


async def _seed_stat_db(tenant_id, *, platform, trips, earnings, hours, period_end):
    eng, sf = _sf()
    try:
        async with sf() as db:
            return await platform_stats.save_stat(
                db,
                tenant_id=tenant_id,
                platform=platform,
                period_label="seed",
                period_start=None,
                period_end=period_end,
                trips=trips,
                earnings=earnings,
                online_hours=hours,
                currency="USD",
            )
    finally:
        await eng.dispose()


async def _seed_ride(tenant_id, *, fare, status, scheduled: dt.date, paid=False):
    eng, sf = _sf()
    try:
        async with sf() as db:
            ride = Ride(
                tenant_id=tenant_id,
                status=status,
                paid=paid,
                pickup_text="Aurora, CO",
                dropoff_text="DEN",
                fare_total=fare,
                duration_minutes=20.0,
                passenger_name="Seed Pax",
                scheduled_at=dt.datetime(
                    scheduled.year, scheduled.month, scheduled.day, 12, tzinfo=dt.UTC
                ),
            )
            db.add(ride)
            await db.commit()
            await db.refresh(ride)
            return ride.id
    finally:
        await eng.dispose()


async def _summary(tenant_id, days=30):
    eng, sf = _sf()
    try:
        async with sf() as db:
            return await platform_stats.summary(db, tenant_id=tenant_id, days=days)
    finally:
        await eng.dispose()


def test_summary_comparison_and_aggregation():
    tid = _run(_mk_tenant("pi-compare"))
    today = _today()
    iso = today.isoformat()
    _run(_seed_stat_db(tid, platform="uber", trips=40, earnings=800, hours=30, period_end=iso))
    _run(_seed_stat_db(tid, platform="lyft", trips=10, earnings=200, hours=8, period_end=iso))
    # Private earned revenue in window: 300 + 200 = 500; cancelled 999 must NOT count.
    _run(_seed_ride(tid, fare=300, status=RideStatus.COMPLETED, scheduled=today))
    _run(_seed_ride(tid, fare=200, status=RideStatus.COMPLETED, scheduled=today))
    _run(_seed_ride(tid, fare=999, status=RideStatus.CANCELLED, scheduled=today))

    s = _run(_summary(tid, days=30))

    # platform totals across both apps
    assert s["totals"]["earnings"] == 1000.0
    assert s["totals"]["trips"] == 50
    assert s["totals"]["online_hours"] == 38.0
    assert s["totals"]["per_trip"] == 20.0  # 1000 / 50
    assert s["totals"]["per_hour"] == round(1000 / 38, 2)  # 26.32

    # per-platform breakdown sorted by earnings desc
    bp = s["by_platform"]
    assert [p["platform"] for p in bp] == ["uber", "lyft"]
    assert bp[0]["earnings"] == 800.0 and bp[0]["trips"] == 40
    assert bp[1]["earnings"] == 200.0 and bp[1]["trips"] == 10

    # platform-vs-private comparison (the core pitch)
    assert s["private_revenue"] == 500.0
    assert s["comparison"]["platform"] == 1000.0
    assert s["comparison"]["private"] == 500.0
    assert s["comparison"]["private_share"] == round(500 / 1500, 3)  # 0.333


def test_summary_window_excludes_old_and_includes_null_periodend():
    tid = _run(_mk_tenant("pi-window"))
    today = _today()
    old = (today - dt.timedelta(days=90)).isoformat()
    # In window (period_end today): 100. Old (90d ago): 999 -> excluded from 30d window.
    _run(
        _seed_stat_db(
            tid, platform="uber", trips=5, earnings=100, hours=4, period_end=today.isoformat()
        )
    )
    _run(_seed_stat_db(tid, platform="uber", trips=99, earnings=999, hours=50, period_end=old))
    # Null period_end -> attributed to created_at (today) -> included.
    _run(_seed_stat_db(tid, platform="lyft", trips=3, earnings=50, hours=2, period_end=None))

    s = _run(_summary(tid, days=30))
    assert s["totals"]["earnings"] == 150.0  # 100 + 50, NOT 999
    assert s["totals"]["trips"] == 8

    # A wide window picks up the old one too.
    s_all = _run(_summary(tid, days=365))
    assert s_all["totals"]["earnings"] == 1149.0


def test_summary_tenant_isolation():
    a = _run(_mk_tenant("pi-iso-a"))
    b = _run(_mk_tenant("pi-iso-b"))
    today = _today()
    _run(
        _seed_stat_db(
            a, platform="uber", trips=20, earnings=500, hours=15, period_end=today.isoformat()
        )
    )
    _run(_seed_ride(a, fare=400, status=RideStatus.COMPLETED, scheduled=today))

    sb = _run(_summary(b, days=30))
    assert sb["totals"]["earnings"] == 0.0  # tenant A platform stats do not leak
    assert sb["totals"]["trips"] == 0
    assert sb["private_revenue"] == 0.0  # tenant A rides do not leak
    assert sb["comparison"]["private_share"] is None  # nothing on either side


def test_per_trip_per_hour_none_when_no_trips_or_hours():
    tid = _run(_mk_tenant("pi-zero"))
    today = _today()
    # earnings present but no trips and no hours -> per_trip / per_hour are None (no div-by-zero).
    _run(
        _seed_stat_db(
            tid,
            platform="other",
            trips=None,
            earnings=120,
            hours=None,
            period_end=today.isoformat(),
        )
    )
    s = _run(_summary(tid, days=30))
    assert s["totals"]["earnings"] == 120.0
    assert s["totals"]["trips"] == 0
    assert s["totals"]["per_trip"] is None
    assert s["totals"]["per_hour"] is None
    # paid (not completed) private ride still counts as earned.
    _run(_seed_ride(tid, fare=90, status=RideStatus.CONFIRMED, scheduled=today, paid=True))
    s2 = _run(_summary(tid, days=30))
    assert s2["private_revenue"] == 90.0
