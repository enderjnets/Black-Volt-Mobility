"""Booking API tests. DB-backed — run with Postgres available (CI service /
compose db). Uses the same auth env as test_auth_api so cookies interoperate."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _owner():
    """A TestClient carrying an owner session cookie."""
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def test_quote_open_for_anonymous():
    # Registration wall OFF by default: an anonymous visitor CAN price a trip up front
    # (conversion-friendly for paid traffic). Lead attribution still binds at booking.
    r = client.post("/api/v1/quote", json={"pickup": "Cherry Creek", "dropoff": "Union Station"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] > 0


def test_quote_prices_trip():
    c = _owner()
    r = c.post("/api/v1/quote", json={"pickup": "Cherry Creek", "dropoff": "Union Station"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] > 0
    assert body["distance_miles"] > 0
    assert body["route_simulated"] is True
    assert body["is_airport"] is False


def test_quote_den_airport_is_metro_flat():
    c = _owner()
    r = c.post(
        "/api/v1/quote", json={"pickup": "Downtown Denver", "dropoff": "Denver Intl (DEN)"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # DEN now folds into the Denver-metro flat zone ($110), not the old airport floor.
    assert body["is_airport"] is False
    assert body["zone"] == "denver_metro"
    assert body["total"] == 110.0


def test_places_autocomplete():
    r = client.get("/api/v1/places/autocomplete", params={"q": "boulder"})
    assert r.status_code == 200
    assert isinstance(r.json()["suggestions"], list)


def test_rate_config_get_defaults():
    r = client.get("/api/v1/rate-config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["airport_flat"] == 74.0
    assert body["per_mile"] == 2.4


def test_rate_config_update_requires_staff():
    # No cookie + AUTH_ENABLED → 401.
    r = client.put("/api/v1/rate-config", json={"per_mile": 3.0})
    assert r.status_code == 401


def test_rate_config_update_as_owner():
    c = _owner()
    r = c.put("/api/v1/rate-config", json={"per_mile": 3.1, "minimum": 30})
    assert r.status_code == 200, r.text
    assert r.json()["per_mile"] == 3.1
    # restore so other tests see defaults
    c.put("/api/v1/rate-config", json={"per_mile": 2.4, "minimum": 28})


def test_create_list_and_patch_ride_as_owner():
    c = _owner()
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek",
            "dropoff": "Denver Intl (DEN)",
            "pax": 2,
            "passenger_name": "Test Rider",
            "flight_number": "UA 2293",
        },
    )
    assert r.status_code == 201, r.text
    ride = r.json()
    assert ride["status"] == "quoted"
    assert ride["fare_total"] > 0
    # Cherry Creek → DEN is now the Denver-metro flat zone ($120).
    assert ride["price_breakdown"]["zone"] == "denver_metro"
    rid = ride["id"]

    lst = c.get("/api/v1/rides")
    assert lst.status_code == 200
    assert any(x["id"] == rid for x in lst.json()["rides"])

    patched = c.patch(f"/api/v1/rides/{rid}", json={"status": "confirmed"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "confirmed"


def test_fare_override_pins_amount():
    c = _owner()
    r = c.post(
        "/api/v1/rides",
        json={"pickup": "Aurora", "dropoff": "Boulder", "fare_override": 95.0, "confirm": True},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["fare_total"] == 95.0
    assert body["status"] == "confirmed"


def test_rides_list_requires_auth():
    r = client.get("/api/v1/rides")
    assert r.status_code == 401


def test_get_missing_ride_404():
    c = _owner()
    r = c.get("/api/v1/rides/99999999")
    assert r.status_code == 404


def test_create_ride_tolerates_long_flight_and_loose_lang():
    """Real/AI data: full airline name in flight + 'Spanish' lang must NOT 422.
    flight is stored (<=40) and lang normalizes to ES. (Regression: Demetra ride
    that silently failed with a 422.)"""
    c = _owner()
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "14681 Saddlebred Ave, Parker, CO",
            "dropoff": "Denver Intl (DEN)",
            "passenger_name": "Demetra Sullivan",
            "flight_number": "United Airlines UA 2766",
            "lang": "Spanish",
            "confirm": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["flight_number"] == "United Airlines UA 2766"
    assert body["lang"] == "ES"
    detail = c.get(f"/api/v1/rides/{body['id']}").json()
    assert detail["flight_number"] == "United Airlines UA 2766"


def test_edit_ride_loose_lang_normalizes():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "Aurora", "dropoff": "DEN", "confirm": True},
    ).json()["id"]
    r = c.patch(
        f"/api/v1/rides/{rid}",
        json={"lang": "english", "flight_number": "American AA 100"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["lang"] == "EN"
