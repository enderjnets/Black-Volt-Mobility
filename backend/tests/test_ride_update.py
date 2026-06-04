"""Smart update of existing rides: editable PATCH, re-quote, conflict preview."""
import os
from datetime import UTC, datetime, timedelta

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["CALENDAR_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _mk(c: TestClient, pickup: str, dropoff: str, when: datetime) -> int:
    r = c.post(
        "/api/v1/rides",
        json={"pickup": pickup, "dropoff": dropoff, "scheduled_at": when.isoformat(),
              "confirm": True},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_patch_edits_route_and_requotes():
    c = _owner()
    when = datetime.now(UTC) + timedelta(days=3, hours=2)
    rid = _mk(c, "Aurora, CO", "Denver Intl (DEN)", when)
    before = c.get(f"/api/v1/rides/{rid}").json()
    r = c.patch(f"/api/v1/rides/{rid}", json={"pickup": "Boulder, CO", "dropoff": "Union Station"})
    assert r.status_code == 200, r.text
    after = c.get(f"/api/v1/rides/{rid}").json()
    assert after["pickup"] == "Boulder, CO"
    assert after["dropoff"] == "Union Station"
    # Different endpoints → simulated route changes → distance re-quoted.
    assert after["distance_miles"] != before["distance_miles"]
    # Calendar event survives the edit (re-synced, not dropped).
    assert after["google_event_id"]


def test_patch_reschedule():
    c = _owner()
    when = datetime.now(UTC) + timedelta(days=4)
    rid = _mk(c, "Aurora, CO", "Denver Intl (DEN)", when)
    new = (when + timedelta(hours=5)).isoformat()
    r = c.patch(f"/api/v1/rides/{rid}", json={"scheduled_at": new})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/v1/rides/{rid}").json()["scheduled_at"][:16] == new[:16]


def test_patch_keeps_status_and_payment_path():
    c = _owner()
    when = datetime.now(UTC) + timedelta(days=5)
    rid = _mk(c, "Cherry Creek", "DEN", when)
    r = c.patch(f"/api/v1/rides/{rid}", json={"pax": 4, "payment_method": "venmo", "paid": True})
    assert r.status_code == 200, r.text
    d = c.get(f"/api/v1/rides/{rid}").json()
    assert d["pax"] == 4 and d["payment_method"] == "venmo" and d["paid"] is True


def test_preview_detects_conflict_and_does_not_persist():
    c = _owner()
    base = datetime.now(UTC) + timedelta(days=6, hours=3)
    a = _mk(c, "Aurora, CO", "Denver Intl (DEN)", base)
    b = _mk(c, "Boulder, CO", "Union Station", base + timedelta(hours=8))
    # Move B onto A's slot → conflict with A.
    r = c.post(f"/api/v1/rides/{b}/preview-update", json={"scheduled_at": base.isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(x["id"] == a for x in body["conflicts"]), body["conflicts"]
    assert body["proposed"]["scheduled_at"][:16] == base.isoformat()[:16]
    # Dry-run: B is unchanged on disk.
    assert c.get(f"/api/v1/rides/{b}").json()["scheduled_at"][:16] != base.isoformat()[:16]


def test_preview_no_conflict_when_far_apart():
    c = _owner()
    base = datetime.now(UTC) + timedelta(days=7)
    _mk(c, "Aurora, CO", "Denver Intl (DEN)", base)
    b = _mk(c, "Boulder, CO", "Union Station", base + timedelta(hours=10))
    r = c.post(
        f"/api/v1/rides/{b}/preview-update",
        json={"scheduled_at": (base + timedelta(days=2)).isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["conflicts"] == []


def test_conflict_excludes_cancelled():
    c = _owner()
    base = datetime.now(UTC) + timedelta(days=8, hours=1)
    a = _mk(c, "Aurora, CO", "Denver Intl (DEN)", base)
    b = _mk(c, "Boulder, CO", "Union Station", base + timedelta(hours=9))
    c.patch(f"/api/v1/rides/{a}", json={"status": "cancelled"})
    r = c.post(f"/api/v1/rides/{b}/preview-update", json={"scheduled_at": base.isoformat()})
    assert r.status_code == 200, r.text
    assert all(x["id"] != a for x in r.json()["conflicts"])


def test_preview_requires_staff():
    c = TestClient(app)  # no session
    r = c.post("/api/v1/rides/1/preview-update", json={"pax": 2})
    assert r.status_code == 401
