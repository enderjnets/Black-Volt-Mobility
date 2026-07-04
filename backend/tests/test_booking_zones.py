"""build_quote integration: flat-rate zones flow end-to-end through the booking
service (maps → zone match → pricing), including per-tenant price overrides.

Isolated-tenant + deterministic (MAPS_SIMULATED): each test uses its own tenant and
asserts exact numbers, so results don't depend on other data.
"""

import asyncio
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

from app.models import Tenant  # noqa: E402
from app.services import booking  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


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


async def _quote(tenant_id, pickup, dropoff):
    eng, sf = _sf()
    try:
        async with sf() as db:
            return await booking.build_quote(
                db, tenant_id=tenant_id, pickup=pickup, dropoff=dropoff
            )
    finally:
        await eng.dispose()


async def _set_zone_prices(tenant_id, prices):
    eng, sf = _sf()
    try:
        async with sf() as db:
            await booking.update_rate_config(
                db, tenant_id=tenant_id, changes={"zone_prices": prices}
            )
    finally:
        await eng.dispose()


def test_build_quote_applies_zone_flat():
    tid = _run(_mk_tenant("bz-aspen"))
    q = _run(_quote(tid, "6000 S Fraser St, Aurora, CO, USA", "Aspen, CO 81611, USA"))
    assert q["total"] == 790.0
    assert q["zone"] == "aspen"
    assert q["is_airport"] is False


def test_build_quote_metro_flat_for_local_ride():
    tid = _run(_mk_tenant("bz-metro"))
    q = _run(_quote(tid, "Aurora, CO, USA", "Cherry Creek, Denver, CO, USA"))
    assert q["total"] == 110.0
    assert q["zone"] == "denver_metro"


def test_build_quote_per_tenant_override():
    tid = _run(_mk_tenant("bz-override"))
    _run(_set_zone_prices(tid, {"aspen": 850.0}))
    q = _run(_quote(tid, "Denver, CO, USA", "Aspen, CO, USA"))
    assert q["total"] == 850.0
    assert q["zone"] == "aspen"


def test_build_quote_out_of_zone_is_metered():
    tid = _run(_mk_tenant("bz-metered"))
    q = _run(_quote(tid, "Grand Junction, CO, USA", "Montrose, CO, USA"))
    assert q["zone"] is None
    # Metered fare from the simulated route; just assert it's a positive metered number,
    # not a flat zone price.
    assert q["total"] > 0
    assert q["total"] not in (110.0, 180.0, 249.0, 280.0, 349.0, 359.0, 390.0, 790.0)
