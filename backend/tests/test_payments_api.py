"""Payments API tests in SIMULATED mode (no real Square calls). Same auth env as
the other API tests."""
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


def _make_ride(c) -> int:
    r = c.post(
        "/api/v1/rides",
        json={"pickup": "Cherry Creek", "dropoff": "Denver Intl (DEN)", "pax": 1},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_payments_config():
    r = client.get("/api/v1/payments/config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["live"] is False  # simulated


def test_authorize_capture_flow():
    c = _owner()
    ride_id = _make_ride(c)
    # authorize
    r = c.post("/api/v1/payments", json={"ride_id": ride_id, "source_id": "cnon:card-nonce-ok"})
    assert r.status_code == 201, r.text
    pay = r.json()
    assert pay["status"] == "authorized"
    assert pay["simulated"] is True
    assert pay["square_payment_id"].startswith("SIMUL-")
    pid = pay["id"]

    # ride should now be confirmed
    ride = c.get(f"/api/v1/rides/{ride_id}").json()
    assert ride["status"] == "confirmed"

    # capture
    r = c.post(f"/api/v1/payments/{pid}/capture")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "captured"

    # capture again → conflict (already captured)
    r = c.post(f"/api/v1/payments/{pid}/capture")
    assert r.status_code == 409


def test_refund_flow():
    c = _owner()
    ride_id = _make_ride(c)
    pid = c.post(
        "/api/v1/payments", json={"ride_id": ride_id, "source_id": "cnon:card-nonce-ok"}
    ).json()["id"]
    # refund before capture → conflict
    assert c.post(f"/api/v1/payments/{pid}/refund", json={}).status_code == 409
    # capture then refund
    c.post(f"/api/v1/payments/{pid}/capture")
    r = c.post(f"/api/v1/payments/{pid}/refund", json={"reason": "test"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "refunded"
    assert body["square_refund_id"].startswith("SIMUL-RF-")


def test_authorize_requires_auth():
    r = client.post("/api/v1/payments", json={"ride_id": 1, "source_id": "x"})
    assert r.status_code == 401


def test_capture_requires_staff():
    r = client.post("/api/v1/payments/1/capture")
    assert r.status_code == 401


def test_authorize_missing_ride_404():
    c = _owner()
    r = c.post("/api/v1/payments", json={"ride_id": 9999999, "source_id": "x"})
    assert r.status_code == 404
