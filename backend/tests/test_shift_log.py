"""One-tap shift logging: segments open/close, offers, DEN lot, idempotent retries."""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"
os.environ["DEMAND_ENABLED"] = "true"
os.environ["DEN_LOT_LAT"] = "39.8000"
os.environ["DEN_LOT_LNG"] = "-104.7000"
os.environ["DEMAND_HOME_LAT"] = "39.60000"
os.environ["DEMAND_HOME_LNG"] = "-104.80000"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import shift_log  # noqa: E402

client = TestClient(app)
CHERRY_CREEK = (39.7170, -104.9530)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _ev(c: TestClient, kind: str, at: str, **extra) -> dict:
    body = {"client_event_id": str(uuid.uuid4()), "kind": kind, "at": at, **extra}
    r = c.post("/api/v1/demand/log", json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_log_requires_staff():
    assert client.post("/api/v1/demand/log", json={}).status_code == 401
    assert client.get("/api/v1/demand/log/today").status_code == 401


def test_in_den_lot_uses_configured_circle():
    assert shift_log.in_den_lot(39.8001, -104.7001)
    assert not shift_log.in_den_lot(*CHERRY_CREEK)
    assert not shift_log.in_den_lot(None, None)


def test_sequence_closes_segments_with_durations():
    c = _owner()
    lat, lng = CHERRY_CREEK
    _ev(c, "online", "2026-09-15T14:00:00Z", lat=lat, lng=lng)
    _ev(c, "ping", "2026-09-15T14:01:00Z", lat=lat, lng=lng)
    off = _ev(c, "offer", "2026-09-15T14:20:00Z", lat=lat, lng=lng, product="black", accepted=True)
    assert off["product"] == "black" and off["accepted"] is True and off["h3_r8"]
    _ev(c, "offline", "2026-09-15T14:45:00Z", lat=lat, lng=lng)
    t = c.get("/api/v1/demand/log/today", params={"date": "2026-09-15"}).json()
    kinds = [e["kind"] for e in t["events"]]
    assert kinds == ["offline", "offer", "online"]  # pings are not listed
    assert t["state"] == "offline" and t["open_since"] is None
    # The open segment ran 14:00→14:20 (20 min), then enroute 14:20→14:45.
    segs = t["segments"]
    assert [(s["state"], s["minutes"]) for s in segs] == [("open", 20.0), ("enroute", 25.0)]


def test_offer_without_position_is_stored_and_flagged():
    c = _owner()
    e = _ev(c, "offer", "2026-09-16T01:00:00Z", product="comfort", accepted=False)
    assert e["no_position"] is True and e["h3_r8"] is None


def test_duplicate_client_event_id_returns_same_row_with_200():
    c = _owner()
    body = {"client_event_id": str(uuid.uuid4()), "kind": "offer",
            "at": "2026-09-16T02:00:00Z", "product": "black_suv", "accepted": True}
    r1 = c.post("/api/v1/demand/log", json=body)
    r2 = c.post("/api/v1/demand/log", json=body)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_here_inside_den_lot_tags_zone():
    c = _owner()
    e = _ev(c, "here", "2026-09-16T03:00:00Z", lat=39.8001, lng=-104.7001)
    assert e["zone_key"] == "den_lot"


def test_home_tag():
    c = _owner()
    home = _ev(c, "online", "2026-09-16T05:00:00Z", lat=39.60000, lng=-104.80000)
    assert home["zone_key"] == "home"
    away = _ev(c, "online", "2026-09-16T05:05:00Z", lat=39.61000, lng=-104.80000)
    assert away["zone_key"] is None
    here = _ev(c, "here", "2026-09-16T05:10:00Z", lat=39.8001, lng=-104.7001)
    assert here["zone_key"] == "den_lot"


def test_bad_kind_and_product_are_422():
    c = _owner()
    r = c.post("/api/v1/demand/log",
               json={"client_event_id": "x", "kind": "teleport", "at": "2026-09-16T04:00:00Z"})
    assert r.status_code == 422
    r = c.post("/api/v1/demand/log",
               json={"client_event_id": "y", "kind": "offer", "product": "helicopter"})
    assert r.status_code == 422
