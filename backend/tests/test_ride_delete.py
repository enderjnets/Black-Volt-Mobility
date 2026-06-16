"""Tests for DELETE /rides/{id} — only cancelled/no-show rides are deletable."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _make_ride(c, name="Del Rider"):
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek",
            "dropoff": "Denver Intl (DEN)",
            "pax": 1,
            "passenger_name": name,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_delete_requires_staff():
    assert client.delete("/api/v1/rides/1").status_code == 401


def test_delete_cancelled_ride():
    c = _owner()
    rid = _make_ride(c)
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "cancelled"}).status_code == 200
    assert c.delete(f"/api/v1/rides/{rid}").status_code == 204
    # It's gone.
    assert c.get(f"/api/v1/rides/{rid}").status_code == 404
    # Deleting again is a clean 404.
    assert c.delete(f"/api/v1/rides/{rid}").status_code == 404


def test_delete_no_show_ride():
    c = _owner()
    rid = _make_ride(c)
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "no_show"}).status_code == 200
    assert c.delete(f"/api/v1/rides/{rid}").status_code == 204


def test_cannot_delete_active_ride():
    c = _owner()
    rid = _make_ride(c)  # default status is QUOTED (active)
    r = c.delete(f"/api/v1/rides/{rid}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "ride_not_deletable"
    # Still there.
    assert c.get(f"/api/v1/rides/{rid}").status_code == 200


def test_cannot_delete_completed_ride():
    c = _owner()
    rid = _make_ride(c)
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "completed"}).status_code == 200
    assert c.delete(f"/api/v1/rides/{rid}").status_code == 409


def test_delete_missing_ride_is_404():
    c = _owner()
    assert c.delete("/api/v1/rides/99999999").status_code == 404
