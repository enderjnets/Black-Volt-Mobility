"""Client (passenger) notifications feed — the passenger bell.

Covers the new driver->client fan-out (a driver's ride message now records an
in-app client notification, not only a push), per-client scoping (one passenger
never sees or mutates another's notifications), unread / read / read-all, and the
require_passenger guard. Runs against the isolated blackvolt_test DB, never prod.
"""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["EMAIL_SIMULATED"] = "true"
os.environ["VAPID_PUBLIC_KEY"] = "test-public"
os.environ["VAPID_PRIVATE_KEY"] = "test-private"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import push, ratelimit  # noqa: E402
from tests.test_ride_messages_api import (  # noqa: E402
    _make_ride,
    _passenger_client,
    _seed_client_in,
    _seed_tenant_client,
    _staff_client,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # Fresh rate-limit state per test (ride ids repeat across tests after RESTART
    # IDENTITY), and no real push — we assert on the in-app row, not the network.
    ratelimit.reset()
    monkeypatch.setattr(push, "notify_client", lambda *a, **k: None)
    monkeypatch.setattr(push, "notify_staff", lambda *a, **k: None)
    yield
    ratelimit.reset()


def _list(client: TestClient) -> dict:
    r = client.get("/api/v1/client/notifications")
    assert r.status_code == 200, r.text
    return r.json()


def _send(client: TestClient, ride: int, body: str) -> None:
    r = client.post(f"/api/v1/rides/{ride}/messages", json={"body": body})
    assert r.status_code == 201, r.text


def test_driver_message_creates_client_notification():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    _send(_staff_client(tid), ride, "on my way")

    data = _list(_passenger_client(cid, tid))
    assert data["unread"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["kind"] == "ride_message"
    assert item["read"] is False
    assert item["data"]["ride_id"] == ride


def test_passenger_own_message_does_not_notify_self():
    # A passenger's message routes to the driver bell, never the passenger's own.
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    passenger = _passenger_client(cid, tid)
    _send(passenger, ride, "hi driver")
    assert _list(passenger)["unread"] == 0


def test_notifications_scoped_per_client():
    cid, tid = _seed_tenant_client()
    other = _seed_client_in(tid)
    ride = _make_ride(tid, cid)
    _send(_staff_client(tid), ride, "yo")

    # A different passenger in the same tenant sees nothing.
    assert _list(_passenger_client(other, tid))["unread"] == 0
    # The addressed passenger sees exactly one.
    assert _list(_passenger_client(cid, tid))["unread"] == 1


def test_mark_read_and_read_all():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    staff = _staff_client(tid)
    _send(staff, ride, "m1")
    _send(staff, ride, "m2")

    passenger = _passenger_client(cid, tid)
    data = _list(passenger)
    assert data["unread"] == 2
    first = data["items"][0]["id"]

    assert passenger.post(f"/api/v1/client/notifications/{first}/read").status_code == 200
    assert _list(passenger)["unread"] == 1

    assert passenger.post("/api/v1/client/notifications/read-all").status_code == 200
    assert _list(passenger)["unread"] == 0


def test_mark_read_foreign_notification_404():
    cid, tid = _seed_tenant_client()
    other = _seed_client_in(tid)
    ride = _make_ride(tid, cid)
    _send(_staff_client(tid), ride, "hey")

    nid = _list(_passenger_client(cid, tid))["items"][0]["id"]
    # The other passenger cannot mark someone else's notification read.
    r = _passenger_client(other, tid).post(f"/api/v1/client/notifications/{nid}/read")
    assert r.status_code == 404


def test_requires_passenger():
    _cid, tid = _seed_tenant_client()
    # Anonymous → 401.
    assert TestClient(app).get("/api/v1/client/notifications").status_code == 401
    # Staff session (no client id) → 403.
    assert _staff_client(tid).get("/api/v1/client/notifications").status_code == 403
