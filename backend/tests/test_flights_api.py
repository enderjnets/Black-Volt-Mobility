"""Flights API. DB-backed — same auth env as the other API tests so cookies interoperate.

The cases are the states the screen actually meets in this database: a drop-off at DEN, a
pickup at DEN, a flight number with no airline (eight of them are stored today), a flight
number on a ride that never goes near an airport, and a booked flight with no time at all.
None of them may 500, and none of them may be dropped without being counted.
"""
import os
from datetime import UTC, datetime, timedelta

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _at(hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def _ride(c, **kw) -> int:
    body = {"confirm": True, **kw}
    r = c.post("/api/v1/rides", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _flights(c, **params):
    r = c.get("/api/v1/flights/upcoming", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _find(body, ride_id):
    return next((f for f in body["flights"] if f["ride_id"] == ride_id), None)


def test_a_drop_off_at_den_is_a_departure_with_its_airline_resolved():
    c = _owner()
    rid = _ride(
        c,
        pickup="14681 Saddlebred Ave, Parker, CO",
        dropoff="Denver Intl (DEN)",
        passenger_name="Demetra Sullivan",
        flight_number="UA 1377",
        scheduled_at=_at(20),
    )
    f = _find(_flights(c), rid)
    assert f is not None
    assert f["direction"] == "departure"
    assert f["carrier"] == "UA"
    assert f["airline"] == "United Airlines"
    assert f["code"] == "UA 1377"
    assert f["needs_airline"] is False
    # Pickup + the ride's own duration: when the passenger reaches the terminal. It is
    # not a "leave home" time and must never be presented as one.
    assert f["airport_eta"] is not None
    assert f["airport_eta"] > f["scheduled_at"]


def test_a_pickup_at_den_is_an_arrival_and_has_no_terminal_eta():
    c = _owner()
    rid = _ride(
        c,
        pickup="Denver Intl (DEN)",
        dropoff="14681 Saddlebred Ave, Parker, CO",
        flight_number="UA 2857",
        scheduled_at=_at(22),
    )
    f = _find(_flights(c), rid)
    assert f is not None
    assert f["direction"] == "arrival"
    assert f["airport_eta"] is None


def test_a_number_with_no_airline_is_reported_never_guessed():
    """Two of the owner's four upcoming rides are exactly this. There is a 976 at every
    carrier, so inventing one would send him to the wrong terminal on a real morning."""
    c = _owner()
    rid = _ride(
        c,
        pickup="10020 Trainstation Circle, Lone Tree, CO",
        dropoff="Denver Intl (DEN)",
        flight_number="976",
        scheduled_at=_at(10),
    )
    body = _flights(c)
    f = _find(body, rid)
    assert f is not None
    assert f["needs_airline"] is True
    assert f["carrier"] is None
    assert f["airline"] is None
    assert f["number"] == 976
    assert f["code"] == "976"
    assert body["missing_airline"] >= 1


def test_a_flight_number_on_a_city_ride_stays_off_the_screen_but_is_counted():
    c = _owner()
    rid = _ride(
        c,
        pickup="Cherry Creek",
        dropoff="Union Station",
        flight_number="UA 999",
        scheduled_at=_at(8),
    )
    body = _flights(c)
    assert _find(body, rid) is None
    assert body["skipped"]["not_an_airport_ride"] >= 1


def test_a_booked_flight_with_no_time_does_not_take_the_screen_down():
    """The nullable column that is null exactly while the thing is still being arranged.
    An unscheduled ride cannot be ordered by an hour it does not have — it must neither
    crash the list nor vanish without a number saying so."""
    c = _owner()
    rid = _ride(
        c,
        pickup="Aurora",
        dropoff="Denver Intl (DEN)",
        flight_number="UA 1602",
    )
    body = _flights(c)
    assert _find(body, rid) is None
    assert body["skipped"]["no_scheduled_time"] >= 1


def test_the_list_is_ordered_soonest_first():
    c = _owner()
    late = _ride(
        c, pickup="Parker, CO", dropoff="Denver Intl (DEN)",
        flight_number="UA 4027", scheduled_at=_at(40),
    )
    soon = _ride(
        c, pickup="Parker, CO", dropoff="Denver Intl (DEN)",
        flight_number="WN 3018", scheduled_at=_at(4),
    )
    ids = [f["ride_id"] for f in _flights(c)["flights"]]
    assert ids.index(soon) < ids.index(late)


def test_a_flight_beyond_the_window_is_not_shown():
    c = _owner()
    rid = _ride(
        c, pickup="Parker, CO", dropoff="Denver Intl (DEN)",
        flight_number="DL 0346", scheduled_at=_at(30),
    )
    assert _find(_flights(c, hours=12), rid) is None
    assert _find(_flights(c, hours=72), rid) is not None


def test_with_no_provider_the_payload_says_so_instead_of_inventing_a_status():
    """`live_source` is the promise. A plausible-looking "on time" with nothing behind it
    is the failure this whole screen exists to avoid."""
    c = _owner()
    _ride(
        c, pickup="Parker, CO", dropoff="Denver Intl (DEN)",
        flight_number="UA 1283", scheduled_at=_at(6),
    )
    body = _flights(c)
    assert body["live_source"] == "none"
    assert all(f["live"] is None for f in body["flights"])
