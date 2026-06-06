"""Google Calendar integration tests (SIMULATED — no Google calls)."""
import os
from datetime import UTC, datetime, timedelta

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["CALENDAR_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["DISPATCH_ADDRESS"] = "6000 S Fraser St, Aurora, CO 80016"
os.environ["CALENDAR_INVITEES"] = "margie240478@gmail.com,enderjnets@gmail.com"
os.environ["CALENDAR_BLOCK_BUFFER_MIN"] = "20"

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
        summary="🚗 Pickup Test",
        description="x",
        location="DEN",
        start=datetime.now(UTC),
        end=datetime.now(UTC) + timedelta(hours=1),
    )
    assert eid and eid.startswith("SIM-EVT-")


def test_build_ride_event_pickup_protocol_format():
    # 09:30 UTC = 03:30 Denver (MDT, UTC-6) in June.
    pt = datetime(2026, 6, 14, 9, 30, tzinfo=UTC)
    ev = calendar.build_ride_event(
        client_name="Demetra",
        pickup="Parker, CO",
        dropoff="Denver Intl (DEN)",
        fare=100.0,
        flight="UA 644",
        phone="+1253",
        notes=None,
        pickup_time=pt,
        tz="America/Denver",
    )
    # Title: 🚗 Pickup [Client] [real time] — [Origin] → [Destination]
    assert ev["summary"].startswith("🚗 Pickup Demetra ")
    assert "Parker, CO → Denver Intl (DEN)" in ev["summary"]
    assert "3:30" in ev["summary"]  # real pickup time in the title
    assert "3:30" in ev["description"]  # and in the description
    assert "UA 644" in ev["description"]
    assert ev["location"] == "Parker, CO"


def test_build_ride_event_guest_without_pickup_time():
    ev = calendar.build_ride_event(
        client_name=None,
        pickup="Aurora, CO",
        dropoff="DEN",
        fare=None,
        flight=None,
        phone=None,
        notes=None,
    )
    assert ev["summary"].startswith("🚗 Pickup Guest")
    assert "Aurora, CO → DEN" in ev["summary"]


def test_event_body_has_attendees_and_dual_reminders():
    start = datetime(2026, 6, 14, 9, 0, tzinfo=UTC)
    end = datetime(2026, 6, 14, 11, 0, tzinfo=UTC)
    body = calendar._event_body(
        summary="s",
        description="d",
        location="l",
        start=start,
        end=end,
        tz="America/Denver",
        attendees=["margie240478@gmail.com", "enderjnets@gmail.com"],
        reminders=[{"method": "popup", "minutes": 30}, {"method": "popup", "minutes": 60}],
    )
    assert body["start"]["dateTime"] == start.isoformat()
    assert body["end"]["dateTime"] == end.isoformat()
    assert {a["email"] for a in body["attendees"]} == {
        "margie240478@gmail.com",
        "enderjnets@gmail.com",
    }
    assert {r["minutes"] for r in body["reminders"]["overrides"]} == {30, 60}


def test_calendar_invitees_filters_non_emails():
    from app.config import Settings

    s = Settings(CALENDAR_INVITEES="margie@x.com, garbage ,  , ender@y.com")
    # A malformed entry must be dropped, not poison the whole attendee payload.
    assert s.calendar_invitees == ["margie@x.com", "ender@y.com"]


def test_house_to_house_window():
    from app.services.booking import house_to_house_window

    sched = datetime(2026, 6, 14, 9, 0, tzinfo=UTC)
    start, end = house_to_house_window(sched, lead_min=30, trip_min=40, trail_min=60)
    # Block = leave home (pickup - deadhead) → return home (dropoff + return + buffer).
    assert start == sched - timedelta(minutes=30)
    assert end == sched + timedelta(minutes=100)


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
