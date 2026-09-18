"""Week recompute end-to-end: seeded segments/offers → week_scores → /demand/week."""
import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

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

client = TestClient(app)
CHERRY_CREEK = (39.7170, -104.9530)


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
    AND after this module's tests to be independent of run order either way."""
    _reset_demand_tenant_state()
    yield
    _reset_demand_tenant_state()


def _seed_priors():
    import h3

    async def _run():
        async with get_session_factory()() as db:
            centre = h3.latlng_to_cell(*CHERRY_CREEK, 8)
            for cell in h3.grid_disk(centre, 2):
                await db.merge(HexPrior(h3_r8=cell, affluence=0.8, hotels=2, generators=3,
                                        den_distance_mi=20.0, zone_key="cherry_creek"))
            await db.commit()

    asyncio.run(_run())


def _log(c: TestClient, kind: str, at: datetime, **extra):
    body = {"client_event_id": str(uuid.uuid4()), "kind": kind, "at": at.isoformat(),
            "lat": CHERRY_CREEK[0], "lng": CHERRY_CREEK[1], **extra}
    r = c.post("/api/v1/demand/log", json=body)
    assert r.status_code in (200, 201), r.text


def test_base_profile_from_trips_is_normalized_to_mean_one():
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)  # Tue 06:00 Denver
    trips = [UberTrip(product=UberProduct.BLACK, request_at=t0 + timedelta(minutes=i))
             for i in range(10)]
    prof = demand.base_profile(windows=[], trips=trips, live_rate=None)
    assert len(prof) == 168
    assert abs(sum(prof) / 168 - demand.dm.DEFAULT_BASE_RATE) < 1e-9
    assert prof[24 + 6] > prof[24 + 12]


def test_base_profile_prefers_dispatch_windows():
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    w = DispatchWindow(window_start=t0, window_end=t0 + timedelta(hours=1),
                       minutes_online=60, dispatches=6)
    prof = demand.base_profile(windows=[w], trips=[], live_rate=None)
    assert prof[24 + 6] == max(prof)


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
    # Observed 2 offers / 40 open min (0.05/min) sits below the seeded prior
    # (0.03 base x 4.095 static from affluence=0.8/hotels=2/generators=3 = 0.12285/min),
    # so blending own data pulls 07's estimate below the untouched 03 baseline.
    assert tue7["mean"] < body["grid"][1][3]["mean"]
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



def test_recompute_error_does_not_kill_the_job(monkeypatch):
    from app.services import scheduler

    async def boom(*a, **k):
        raise RuntimeError("compute failed")

    monkeypatch.setattr(demand, "recompute_week", boom)
    asyncio.run(scheduler._demand_week_job())  # must not raise
