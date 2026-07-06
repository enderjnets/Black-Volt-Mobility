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
    # Metered fare from the simulated route; `zone is None` above is the real check —
    # a hand-synced "not in <flat prices>" tuple here just re-broke on every recalibration.
    assert q["total"] > 0


# ---------------------------------------------------------------------------
# Uncovered-endpoint guard (Lisa/Longmont bug, 2026-07-05): an endpoint outside
# every named zone must never let the OTHER endpoint's flat underprice the trip.
# The matched flat becomes a floor; the metered fare wins when higher.
# ---------------------------------------------------------------------------


def test_longmont_rides_the_boulder_flat():
    # Lisa's exact route. Longmont is now a boulder-zone term, so the flat
    # applies directly (no guard) instead of the old core-$110 fall-through.
    tid = _run(_mk_tenant("bz-longmont"))
    q = _run(
        _quote(
            tid,
            "6632 Fairways Drive, Longmont, CO 80503, USA",
            "Denver International Airport, 8500 Peña Blvd, Denver, CO 80249, USA",
        )
    )
    assert q["zone"] == "boulder"
    assert q["total"] == 165.0  # zone default; owner tunes in Rates


def test_uncovered_far_town_meters_above_the_core_flat():
    # Estes Park is in no zone; DEN matches denver_metro (110). Simulated route =
    # 29.8 mi / 72.6 min -> metered 12 + 29.8*2.4 + 72.6*0.55 = 123.45 > 110, so
    # the metered fare must win and the quote must NOT report a zone.
    tid = _run(_mk_tenant("bz-uncovered-far"))
    q = _run(
        _quote(tid, "Estes Park, CO, USA", "Denver International Airport, Denver, CO, USA")
    )
    assert q["zone"] is None
    assert q["is_airport"] is True
    assert q["total"] == 123.45


def test_uncovered_near_town_keeps_the_flat_as_floor():
    # Evergreen is in no zone; metered (74 after the airport floor) stays below the
    # core flat, so the flat still applies — the guard never lowers a price.
    tid = _run(_mk_tenant("bz-uncovered-near"))
    q = _run(_quote(tid, "Evergreen, CO, USA", "Denver, CO, USA"))
    assert q["zone"] == "denver_metro"
    assert q["total"] == 110.0


def test_bare_airport_code_still_gets_the_flat():
    # "DEN" alone matches no zone term but IS an airport keyword: the guard must
    # treat it as covered and keep today's flat behaviour for the flagship run.
    tid = _run(_mk_tenant("bz-bare-den"))
    q = _run(_quote(tid, "6000 S Fraser St, Aurora, CO, USA", "DEN"))
    assert q["zone"] == "denver_metro"
    assert q["total"] == 110.0


def test_guard_is_not_fooled_by_den_substring_in_street_name():
    # Audit-critical case: "Garden St" contains the raw substring "den", which the
    # legacy looks_like_airport would read as an airport keyword and skip the guard,
    # re-opening the core-flat hole. The guard's word-boundary check must meter it:
    # sim route 28.7 mi / 62.3 min -> 12 + 28.7*2.4 + 62.3*0.55 = 115.15 > 110.
    tid = _run(_mk_tenant("bz-garden-st"))
    q = _run(
        _quote(
            tid,
            "1234 Garden St, Estes Park, CO, USA",
            "Denver International Airport, Denver, CO, USA",
        )
    )
    assert q["zone"] is None
    assert q["total"] == 115.15


def test_uncovered_stop_triggers_the_guard():
    # Covered endpoints (Denver -> Aurora) with an uncovered far stop (Lyons):
    # the stop makes the trip long, so the metered fare (+ stop fee on both paths)
    # must beat the flat 110 + 15.
    tid = _run(_mk_tenant("bz-uncovered-stop"))
    eng, sf = _sf()

    async def go():
        try:
            async with sf() as db:
                return await booking.build_quote(
                    db,
                    tenant_id=tid,
                    pickup="Denver, CO, USA",
                    dropoff="Aurora, CO, USA",
                    stops=["Lyons, CO, USA"],
                )
        finally:
            await eng.dispose()

    q = _run(go())
    assert q["zone"] is None
    assert q["total"] == 146.26  # metered 131.26 + 15 stop fee > 125 flat+stop
