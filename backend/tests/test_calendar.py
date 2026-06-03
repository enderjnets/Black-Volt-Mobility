"""Google Calendar integration tests (SIMULATED — no Google calls)."""
import os
from datetime import UTC, datetime, timedelta

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["CALENDAR_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import calendar  # noqa: E402

client = TestClient(app)


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def test_upsert_event_simulated_returns_id():
    eid = calendar.upsert_event(
        summary="Black Volt · Test",
        description="x",
        location="DEN",
        start=datetime.now(UTC),
        duration_min=60,
    )
    assert eid and eid.startswith("SIM-EVT-")


def test_build_ride_event():
    ev = calendar.build_ride_event(
        client_name="Demetra",
        pickup="Parker, CO",
        dropoff="Denver Intl (DEN)",
        fare=100.0,
        flight="UA 644",
        phone="+1253",
        notes=None,
    )
    assert ev["summary"] == "Black Volt · Demetra"
    assert ev["location"] == "Parker, CO"
    assert "DEN" in ev["description"] and "UA 644" in ev["description"]


def test_scheduled_ride_gets_event_id():
    c = _owner()
    when = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Parker, CO",
            "dropoff": "Denver Intl (DEN)",
            "passenger_name": "Demetra",
            "scheduled_at": when,
            "confirm": True,
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    detail = c.get(f"/api/v1/rides/{rid}").json()
    assert detail["google_event_id"], "scheduled ride should get a calendar event id"
    assert detail["google_event_id"].startswith("SIM-EVT-")


def test_cancel_removes_event_id():
    c = _owner()
    when = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "Aurora", "dropoff": "DEN", "scheduled_at": when, "confirm": True},
    ).json()["id"]
    assert c.get(f"/api/v1/rides/{rid}").json()["google_event_id"]
    c.patch(f"/api/v1/rides/{rid}", json={"status": "cancelled"})
    assert c.get(f"/api/v1/rides/{rid}").json()["google_event_id"] is None


def test_unscheduled_ride_no_event():
    c = _owner()
    rid = c.post(
        "/api/v1/rides", json={"pickup": "Cherry Creek", "dropoff": "DEN", "confirm": True}
    ).json()["id"]
    assert c.get(f"/api/v1/rides/{rid}").json()["google_event_id"] is None
