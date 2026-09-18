"""Week recompute end-to-end: seeded segments/offers → week_scores → /demand/week."""
import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from sqlalchemy import delete, select

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"
os.environ["DEMAND_ENABLED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DispatchWindow, HexPrior, UberProduct, UberTrip  # noqa: E402
from app.services import demand  # noqa: E402
from app.services import demand_model as dm  # noqa: E402

client = TestClient(app)
CHERRY_CREEK = (39.7170, -104.9530)


def _cell(lat: float, lng: float) -> str:
    import h3

    return h3.latlng_to_cell(lat, lng, 8)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _tenant_id(c: TestClient) -> int:
    return c.get("/api/v1/auth/me").json()["tenant_id"]


def _dsn() -> str:
    return get_settings().DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _rows(query: str, *args) -> list:
    async def _run():
        conn = await asyncpg.connect(_dsn())
        try:
            return await conn.fetch(query, *args)
        finally:
            await conn.close()

    return asyncio.run(_run())


def _reset_demand_tenant_state():
    tenants = _rows("SELECT id FROM tenants WHERE slug IN ('ender-ocando', 'black-volt')")
    assert tenants, "no tenant matched ender-ocando/black-volt: cleanup would be a silent no-op"
    for row in tenants:
        tid = row["id"]
        _rows("DELETE FROM week_scores WHERE tenant_id = $1", tid)
        _rows("DELETE FROM driver_state_segments WHERE tenant_id = $1", tid)
        _rows("DELETE FROM offer_events WHERE tenant_id = $1", tid)
        _rows("DELETE FROM demand_imports WHERE tenant_id = $1", tid)
        _rows("DELETE FROM uber_trips WHERE tenant_id = $1", tid)
        _rows("DELETE FROM dispatch_windows WHERE tenant_id = $1", tid)


@pytest.fixture(scope="module", autouse=True)
def _cleanup_demand_jobs_tenant_state():
    """This module writes `week_scores`, live `driver_state_segments`/`offer_events`
    (via the log API) and `demand_imports` (plus two `source='gps'` segments) for
    the single default tenant every other DB-touching test file shares (password
    login always resolves to it) — the same sharing test_gps_import.py's fixture
    documents. `recompute_week`'s trip/segment/offer queries have no per-test
    scoping, so this module also resets on SETUP: `test_gps_import.py`'s own import
    test leaves `uber_trips` behind (only its `source='gps'` segments and
    `demand_imports` are cleaned by its fixture) and `test_demand_api.py` has no
    cleanup fixture at all, leaving 2 `source='export'` segments from its ONOFF
    fixture. Neither is ours to fix, so reset the tenant's demand tables before
    AND after this module's tests to be independent of run order either way. Also
    restore `hex_priors` (ruling (e)): that table is shared geography, has no
    `tenant_id`, and `_seed_priors` overwrites ~19 real cells with `db.merge`."""
    _reset_demand_tenant_state()
    yield
    _reset_demand_tenant_state()
    _restore_hex_priors()


_HEX_PRIOR_ORIGINALS: dict[str, dict | None] = {}


def _restore_hex_priors():
    async def _run():
        async with get_session_factory()() as db:
            for cell, original in _HEX_PRIOR_ORIGINALS.items():
                if original is None:
                    await db.execute(delete(HexPrior).where(HexPrior.h3_r8 == cell))
                else:
                    await db.merge(HexPrior(h3_r8=cell, **original))
            await db.commit()

    asyncio.run(_run())
    _HEX_PRIOR_ORIGINALS.clear()


def _seed_priors():
    """Seeds the ~19-cell Cherry Creek disk with fixture values, snapshotting
    whatever was there first (real row or none) so the module teardown can put it
    back — `hex_priors` is shared geography, not tenant-scoped, not truncated by
    conftest (ruling (e))."""
    import h3

    async def _run():
        async with get_session_factory()() as db:
            centre = h3.latlng_to_cell(*CHERRY_CREEK, 8)
            for cell in h3.grid_disk(centre, 2):
                if cell not in _HEX_PRIOR_ORIGINALS:
                    existing = await db.get(HexPrior, cell)
                    _HEX_PRIOR_ORIGINALS[cell] = None if existing is None else {
                        "affluence": existing.affluence,
                        "hotels": existing.hotels,
                        "generators": existing.generators,
                        "den_distance_mi": existing.den_distance_mi,
                        "zone_key": existing.zone_key,
                    }
                await db.merge(HexPrior(h3_r8=cell, affluence=0.8, hotels=2, generators=3,
                                        den_distance_mi=20.0, zone_key="cherry_creek"))
            # The zone must contain ONLY these cells. The exact posterior identity below
            # is computed from a hand-chosen static multiplier, which holds only while
            # the fixture owns the zone — and it did, purely because nobody had ever run
            # build_demand_priors against this database. The moment real priors exist,
            # cherry_creek gains ~15 more cells, `static` becomes their mean, and the
            # test fails for a reason that has nothing to do with the code. Park the
            # strangers by zone, snapshotting them so teardown puts them back.
            disk = set(h3.grid_disk(centre, 2))
            strangers = (await db.execute(
                select(HexPrior).where(HexPrior.zone_key == "cherry_creek")
            )).scalars().all()
            for row in strangers:
                if row.h3_r8 in disk:
                    continue
                if row.h3_r8 not in _HEX_PRIOR_ORIGINALS:
                    _HEX_PRIOR_ORIGINALS[row.h3_r8] = {
                        "affluence": row.affluence, "hotels": row.hotels,
                        "generators": row.generators,
                        "den_distance_mi": row.den_distance_mi, "zone_key": row.zone_key,
                    }
                row.zone_key = None
            await db.commit()

    asyncio.run(_run())


def _seed_lodo_priors():
    """A second scored zone, so "the baseline is global" can actually be tested.

    Deliberately richer than the Cherry Creek fixture: if both zones carried the same
    level, a per-zone baseline and a global one would agree and the test would pass
    either way. Snapshots into the same dict the module teardown restores from, because
    hex_priors is shared geography and conftest never truncates it.
    """
    import h3

    LODO = (39.7527, -104.9998)

    async def _run():
        async with get_session_factory()() as db:
            for cell in h3.grid_disk(h3.latlng_to_cell(*LODO, 8), 2):
                if cell not in _HEX_PRIOR_ORIGINALS:
                    existing = await db.get(HexPrior, cell)
                    _HEX_PRIOR_ORIGINALS[cell] = None if existing is None else {
                        "affluence": existing.affluence,
                        "hotels": existing.hotels,
                        "generators": existing.generators,
                        "den_distance_mi": existing.den_distance_mi,
                        "zone_key": existing.zone_key,
                    }
                await db.merge(HexPrior(h3_r8=cell, affluence=0.95, hotels=8, generators=5,
                                        den_distance_mi=18.0, zone_key="lodo"))
            await db.commit()

    asyncio.run(_run())


def _log(c: TestClient, kind: str, at: datetime, **extra):
    body = {"client_event_id": str(uuid.uuid4()), "kind": kind, "at": at.isoformat(),
            "lat": CHERRY_CREEK[0], "lng": CHERRY_CREEK[1], **extra}
    r = c.post("/api/v1/demand/log", json=body)
    assert r.status_code in (200, 201), r.text


def test_base_profile_from_trips_is_a_bounded_shape_around_the_level():
    # The week mean is deliberately no longer pinned to `level`: clamping each hour's
    # ratio is what keeps an unobserved hour off zero, and that floor lifts the mean.
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)  # Tue 06:00 Denver
    trips = [UberTrip(product=UberProduct.BLACK, request_at=t0 + timedelta(minutes=i))
             for i in range(10)]
    prof = demand.base_profile(windows=[], trips=trips, live_rate=None)
    lo, hi = demand.dm.BASE_SHAPE_RANGE
    level = demand.dm.DEFAULT_BASE_RATE
    assert len(prof) == 168
    assert all(lo * level <= v <= hi * level for v in prof)
    assert prof[24 + 6] > prof[24 + 12]


def test_base_profile_never_claims_an_hour_is_impossible():
    """A spiky history must never read as '0.0% chance of a Black offer': an hour with
    no trip in it is thin evidence, not proof of impossibility."""
    t0 = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)  # Mon 00:00 Denver
    trips = [UberTrip(product=UberProduct.BLACK,
                      request_at=t0 + timedelta(hours=16 * (i % 10)))
             for i in range(30)]
    prof = demand.base_profile(windows=[], trips=trips, live_rate=None)
    lo, hi = demand.dm.BASE_SHAPE_RANGE
    level = demand.dm.DEFAULT_BASE_RATE
    assert not any(v == 0.0 for v in prof)
    assert min(prof) == pytest.approx(lo * level)
    assert max(prof) == pytest.approx(hi * level)
    # The peak used to read 15.1 offers/hour and a 97.7% chance in 15 minutes.
    assert demand.dm.p_within(max(prof)) < 0.85


def test_base_profile_keeps_a_real_day_night_pattern():
    """Bounding the shape must not flatten it: a genuine day/night histogram still has
    to read as contrast, not as one grey week."""
    t0 = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)
    trips = [
        UberTrip(product=UberProduct.BLACK,
                 request_at=t0 + timedelta(days=dow, hours=hour, minutes=m))
        for dow in range(7)
        for hour in range(24)
        for m in range(10 if 7 <= hour <= 20 else 1)
    ]
    prof = demand.base_profile(windows=[], trips=trips, live_rate=None)
    assert max(prof) / min(prof) > 5.0
    assert prof[12] > prof[3]


def test_base_profile_prefers_dispatch_windows():
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    w = DispatchWindow(window_start=t0, window_end=t0 + timedelta(hours=1),
                       minutes_online=60, dispatches=6)
    prof = demand.base_profile(windows=[w], trips=[], live_rate=None)
    assert prof[24 + 6] == max(prof)


def test_base_profile_windows_with_no_minutes_are_not_impossible_hours():
    """The `minutes_online == 0` branch feeds the same shape as the trips histogram:
    an hour the owner was never dispatched in must not come out at exactly zero."""
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)  # Tue 06:00 Denver
    busy = DispatchWindow(window_start=t0, window_end=t0 + timedelta(hours=1),
                          minutes_online=60, dispatches=6)
    idle = DispatchWindow(window_start=t0 + timedelta(hours=5),
                          window_end=t0 + timedelta(hours=6), minutes_online=0, dispatches=0)
    prof = demand.base_profile(windows=[busy, idle], trips=[], live_rate=None)
    lo, hi = demand.dm.BASE_SHAPE_RANGE
    level = demand.dm.DEFAULT_BASE_RATE
    assert not any(v == 0.0 for v in prof)
    assert prof[24 + 11] == pytest.approx(lo * level)
    assert prof[24 + 6] == max(prof) == pytest.approx(hi * level)


def test_event_multipliers_lift_hours_around_the_event():
    now = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)  # Mon 00:00 Denver
    ev = {"title": "Concert", "lat": 39.7487, "lng": -105.0077,  # Ball Arena
          "starts_at": datetime(2026, 9, 15, 1, 0, tzinfo=UTC)}  # Mon 19:00 Denver
    zone = {"key": "downtown", "lat": 39.7392, "lng": -104.9903, "radius_mi": 1.5}
    mult, reasons = demand.event_multipliers([ev], zone, now)
    assert mult[17] > 1.0 and mult[19] > 1.0 and mult[22] > 1.0 and mult[12] == 1.0
    assert "Concert" in reasons[19]
    far = {"key": "boulder", "lat": 40.0150, "lng": -105.2705, "radius_mi": 2.5}
    assert demand.event_multipliers([ev], far, now)[0] == [1.0] * 168


def test_week_has_no_top_blocks_before_any_data():
    """The fresh-tenant path — `week_payload` recomputes on demand for anyone who opens
    the tab before importing anything, so this is the first thing a new driver sees. A
    week with no shape has no defensible 'best block': the UI has to reach its empty
    state instead of five whole-day rows reading '0.0 expected offers'. Every existing
    top_blocks test hand-builds an obvious hot set, which is why none of them caught it.
    """
    _reset_demand_tenant_state()
    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)

    async def _run():
        async with get_session_factory()() as db:
            return await demand.recompute_week(
                db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC)
            )

    assert asyncio.run(_run())["rows"] >= 168
    body = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"}).json()
    assert body["own_minutes_total"] == 0  # precondition: nothing imported, nothing logged
    means = {round(cell["mean"], 12) for row in body["grid"] for cell in row}
    # Precondition, not the claim under test: with no flight baseline and no events
    # every hour carries the same prior, so the week genuinely has no shape.
    assert len(means) == 1 and means.pop() > 0
    assert body["top_blocks"] == []


def test_block_reasons_cover_the_whole_block_not_just_its_first_hour():
    """The row the driver reads has to say why THAT RANGE of hours is worth driving to.

    Reading `grid[dow][start_hour]["reasons"]` answered a narrower question: an event
    that starts at 20:00 inside an 18:00-22:00 block, and any flight bank that misses
    the first hour, vanished from the row. The spec asks each block to carry "the
    covariates that lifted it" - it, the block. Pure function, no DB.
    """
    def cell(flights=1.0, events=None, holiday=None, own_minutes=0.0, own_offers=0.0):
        return {"reasons": {"flights": flights, "events": events or [], "holiday": holiday,
                            "own_minutes": own_minutes, "own_offers": own_offers}}

    grid = [[cell() for _ in range(24)] for _ in range(7)]
    grid[1][18] = cell(own_minutes=30.0, own_offers=1.0)
    grid[1][19] = cell(flights=1.4, own_minutes=15.0)
    grid[1][20] = cell(flights=2.1, events=["Nuggets vs Lakers"], holiday="Labor Day",
                       own_offers=2.0)
    grid[1][21] = cell(events=["Nuggets vs Lakers", "Red Rocks: ODESZA"])

    block = dm.Block(dow=1, start_hour=18, end_hour=22, expected_offers=9.0, mean=0.13)
    r = demand._block_reasons(grid, block)

    assert r["flights"] == 2.1                     # the block's peak, not the first hour's 1.0
    assert r["events"] == ["Nuggets vs Lakers", "Red Rocks: ODESZA"]  # union, deduped, in order
    assert r["holiday"] == "Labor Day"             # per-day, carried by any hour of the block
    assert r["own_minutes"] == 45.0                # 30 + 15: over a block these are totals
    assert r["own_offers"] == 3.0

    # The reading this replaced would have shown none of it, which is the whole point.
    first_hour = grid[1][18]["reasons"]
    assert first_hour["flights"] == 1.0 and first_hour["events"] == []


def test_block_reasons_of_a_quiet_block_stay_empty():
    """The other half: aggregating must not invent a reason where there is none.

    Without this, `flights` defaulting the wrong way or `events` collecting falsy
    entries would still pass the test above.
    """
    quiet = {"reasons": {"flights": 1.0, "events": [], "holiday": None,
                         "own_minutes": 0.0, "own_offers": 0.0}}
    grid = [[dict(quiet) for _ in range(24)] for _ in range(7)]
    block = dm.Block(dow=3, start_hour=6, end_hour=8, expected_offers=2.0, mean=0.1)
    r = demand._block_reasons(grid, block)
    assert r == {"flights": 1.0, "events": [], "holiday": None,
                 "own_minutes": 0.0, "own_offers": 0.0}


def test_a_shift_still_open_does_not_take_the_week_down():
    """The state this whole feature exists for: you tapped Online and have not tapped
    Offline yet.

    Such a segment carries no end_at — it is still happening — and subtracting it raw
    threw `unsupported operand type(s) for -: 'NoneType' and 'datetime.datetime'` out of
    the payload, so the entire Week tab answered 500. It reached production because
    every seeded segment in this file had already been closed, and the endpoint was only
    ever exercised against tidy history.
    """
    from app.models import DriverStateSegment, EarnerState, SegmentSource

    _reset_demand_tenant_state()
    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)
    t = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)
    cell = _cell(*CHERRY_CREEK)

    async def _seed_and_run():
        async with get_session_factory()() as db:
            db.add(DriverStateSegment(
                tenant_id=tid, dedup_key="still-open", state=EarnerState.OPEN,
                begin_at=t, end_at=None, last_ping_at=t + timedelta(minutes=40),
                begin_lat=CHERRY_CREEK[0], begin_lng=CHERRY_CREEK[1], h3_r8=cell,
                source=SegmentSource.LIVE))
            await db.commit()
            return await demand.recompute_week(
                db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC)
            )

    asyncio.run(_seed_and_run())
    r = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"})
    assert r.status_code == 200, r.text
    # And the open minutes still count toward the cell, via the last ping.
    assert r.json()["own_minutes_total"] > 0
    # Neighbours in this file build on whatever state is left behind — the exact posterior
    # identity asserted a few tests down is sensitive to a stray segment.
    _reset_demand_tenant_state()


def test_the_block_ratio_is_measured_against_the_same_baseline_in_every_zone():
    """A per-zone baseline would give every zone's best block roughly the same ratio and
    destroy the only comparison the driver is making. The baseline is the median hour
    across ALL zones, so the number means the same thing wherever it appears.

    Both sides of the ratio come from the model on purpose. Its scale stacks four
    multipliers into peaks an order of magnitude above this driver's real history, and
    dividing a model estimate by a measured rate would be the frame error this feature
    has already made six times. A ratio of two model numbers survives being wrong about
    the scale; the ordering is what was verified.
    """
    _reset_demand_tenant_state()
    _seed_priors()
    _seed_lodo_priors()
    c = _owner()
    tid = _tenant_id(c)

    async def _run():
        async with get_session_factory()() as db:
            return await demand.recompute_week(
                db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC)
            )

    asyncio.run(_run())
    # Discover the scored zones instead of naming them: which ones have cells depends on
    # the seeded priors, and a zone with none answers 404. Asserting on a name that was
    # never scored tests the fixture, not the baseline.
    first = c.get("/api/v1/demand/week")
    assert first.status_code == 200, first.text
    bodies = []
    for z in first.json()["zones"]:
        r = c.get("/api/v1/demand/week", params={"zone": z["key"]})
        if r.status_code == 200:
            bodies.append(r.json())
    assert len(bodies) >= 2, "need at least two scored zones to compare their baselines"

    baselines = {b["baseline_mean"] for b in bodies}
    assert len(baselines) == 1, f"the baseline must be global, got {baselines}"
    assert baselines.pop() > 0

    for body in bodies:
        for blk in body["top_blocks"]:
            assert blk["lift"] == pytest.approx(
                round(blk["mean"] / body["baseline_mean"], 1), abs=1e-9
            )


def test_a_recompute_invalidates_every_cached_zone_for_the_tenant():
    """The sweep has to match the keys, and nothing in the types says it does.

    Adding a payload version between `week` and the tenant id once moved every key out
    from under the invalidator's pattern. Nothing raised: recompute_week returned
    happily, the driver kept the previous week for the length of the TTL, and the only
    symptom was numbers that would not change. Pin the two together.
    """
    assert demand._key(7, "lodo").startswith(demand._key_prefix(7))
    assert demand._key(7, "lodo") == f"{demand._key_prefix(7)}lodo"
    # A tenant's prefix must not be a prefix of another tenant's keys (7 vs 70).
    assert not demand._key(70, "lodo").startswith(demand._key_prefix(7))


def test_recompute_and_week_endpoint():
    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)
    # Two Tuesday-morning waits in Cherry Creek with one Black offer each.
    for day in (8, 15):
        t = datetime(2026, 9, day, 13, 0, tzinfo=UTC)  # Tue 07:00 Denver
        _log(c, "online", t)
        _log(c, "offer", t + timedelta(minutes=20), product="black", accepted=True)
        _log(c, "offline", t + timedelta(minutes=50))

    async def _run(now: datetime):
        async with get_session_factory()() as db:
            return await demand.recompute_week(db, tenant_id=tid, now=now)

    res = asyncio.run(_run(datetime(2026, 9, 16, tzinfo=UTC)))
    assert res["rows"] >= 168 and res["zones"] >= 1

    assert client.get("/api/v1/demand/week").status_code == 401
    r = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["zone"] == "cherry_creek" and len(body["grid"]) == 7 and len(body["grid"][0]) == 24
    tue7 = body["grid"][1][7]
    assert tue7["own_share"] > 0 and 0 < tue7["p15"] < 1
    # Rule 3: both accepted Black offers count (the enroute segments they open are
    # deduped against them, so this is 2, not 4).
    assert tue7["reasons"]["own_offers"] == 2
    # Exact posterior identity: prior 0.03 base x 4.095 static (affluence=0.8,
    # hotels=2, generators=3) = 0.12285/min; y=2 offers, e=40 open min (pseudo=600).
    assert abs(tue7["mean"] - (0.12285 * 600 + 2) / 640) < 1e-9
    assert "top_blocks" in body and "private_rides" in body
    etag1 = r.headers.get("etag")
    assert etag1
    asyncio.run(_run(datetime(2026, 9, 16, 1, tzinfo=UTC)))  # later recompute must move the ETag
    r2 = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"})
    assert r2.headers.get("etag") != etag1
    assert c.get("/api/v1/demand/week", params={"zone": "narnia"}).status_code == 404


def test_gps_coverage_and_home_rules():
    """Addendum A: inside a GPS window live waits are ignored; home never counts."""
    import h3

    from app.models import DemandImport, DriverStateSegment, EarnerState, SegmentSource

    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)
    cell = h3.latlng_to_cell(*CHERRY_CREEK, 8)
    t = datetime(2026, 9, 15, 13, 0, tzinfo=UTC)  # Tue 07:00 Denver
    # A live wait inside the covered window: must not count.
    _log(c, "online", t)
    _log(c, "offline", t + timedelta(minutes=50))

    async def _seed_and_run():
        async with get_session_factory()() as db:
            db.add(DemandImport(tenant_id=tid, summary={"gps": {
                "start": "2026-09-01T00:00:00+00:00", "end": "2026-09-30T00:00:00+00:00"}}))
            db.add(DriverStateSegment(
                tenant_id=tid, dedup_key="gps-open", state=EarnerState.OPEN, begin_at=t,
                end_at=t + timedelta(minutes=50), begin_lat=CHERRY_CREEK[0],
                begin_lng=CHERRY_CREEK[1], h3_r8=cell, source=SegmentSource.GPS))
            db.add(DriverStateSegment(
                tenant_id=tid, dedup_key="gps-home", state=EarnerState.OPEN,
                begin_at=t + timedelta(hours=2), end_at=t + timedelta(hours=2, minutes=50),
                begin_lat=CHERRY_CREEK[0], begin_lng=CHERRY_CREEK[1], h3_r8=cell,
                zone_key="home", source=SegmentSource.GPS))
            await db.commit()
            return await demand.recompute_week(
                db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC)
            )

    asyncio.run(_seed_and_run())
    body = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"}).json()
    assert body["grid"][1][7]["reasons"]["own_minutes"] == 50  # the GPS wait, not 100
    assert body["grid"][1][9]["reasons"]["own_minutes"] == 0  # home excluded
    # "Hours you have logged here" is the raw exposure, never the pooled model input:
    # hour 7's neighbours have nothing logged in them, and used to report the 25
    # minutes and 0.5 offers they borrowed from hour 7.
    for h in (6, 8):
        assert body["grid"][1][h]["reasons"]["own_minutes"] == 0
        assert body["grid"][1][h]["reasons"]["own_offers"] == 0
    assert body["grid"][1][7]["reasons"]["own_offers"] == 2
    assert body["own_minutes_total"] == 50  # the one real wait, not 2x it


def test_gps_enroute_dedupes_against_live_accepted_offer():
    """Addendum A rule 4 (ruling f): a gps enroute segment matched to a premium
    trip request must not double-count once a live accepted offer already covers
    the same acceptance."""
    import h3

    from app.models import DriverStateSegment, EarnerState, SegmentSource

    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)
    cell = h3.latlng_to_cell(*CHERRY_CREEK, 8)
    t = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)  # Tue 14:00 Denver, away from other tests' hours
    _log(c, "offer", t, product="black", accepted=True)

    async def _seed_and_run():
        async with get_session_factory()() as db:
            db.add(UberTrip(tenant_id=tid, dedup_key="rule4-trip", product=UberProduct.BLACK,
                             request_at=t))
            db.add(DriverStateSegment(
                tenant_id=tid, dedup_key="rule4-gps-enroute", state=EarnerState.ENROUTE,
                begin_at=t, end_at=t + timedelta(minutes=10), h3_r8=cell,
                source=SegmentSource.GPS))
            await db.commit()
            return await demand.recompute_week(
                db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC)
            )

    asyncio.run(_seed_and_run())
    dow, hour = divmod(demand.dm.hour_of_week(t), 24)
    body = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"}).json()
    assert body["grid"][dow][hour]["reasons"]["own_offers"] == 1  # not 2: deduped


def test_live_segment_outside_gps_window_still_counts():
    """Addendum A rule 1 negative control (ruling f): a live open segment outside
    every GPS coverage window must still count as exposure."""
    from app.models import DemandImport

    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)
    t = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)  # well before the seeded GPS window
    _log(c, "online", t)
    _log(c, "offline", t + timedelta(minutes=30))

    async def _seed_and_run():
        async with get_session_factory()() as db:
            db.add(DemandImport(tenant_id=tid, summary={"gps": {
                "start": "2026-09-01T00:00:00+00:00", "end": "2026-09-10T00:00:00+00:00"}}))
            await db.commit()
            return await demand.recompute_week(
                db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC)
            )

    asyncio.run(_seed_and_run())
    dow, hour = divmod(demand.dm.hour_of_week(t), 24)
    body = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"}).json()
    assert body["grid"][dow][hour]["reasons"]["own_minutes"] == 30  # the whole wait
    # `> 0` would pass on a neighbour too, which is the bug this has to exclude: the
    # hour before pools half of the 50-minute GPS wait two hours earlier and half of
    # this one, and must still report nothing logged.
    assert body["grid"][dow][hour - 1]["reasons"]["own_minutes"] == 0
    assert body["grid"][dow][hour + 1]["reasons"]["own_minutes"] == 0


def test_recompute_error_does_not_kill_the_job(monkeypatch, caplog):
    from app.services import scheduler

    async def boom(*a, **k):
        raise RuntimeError("compute failed")

    async def fake_tenants_with_data(db):
        return [424242]

    monkeypatch.setattr(demand, "recompute_week", boom)
    monkeypatch.setattr(demand, "tenants_with_data", fake_tenants_with_data)
    caplog.set_level("WARNING", logger="blackvolt.social.scheduler")
    asyncio.run(scheduler._demand_week_job())  # must not raise
    assert "demand week job failed for tenant 424242: compute failed" in caplog.text
