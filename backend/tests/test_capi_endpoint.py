"""The /payments endpoint schedules a Meta CAPI Purchase for card bookings, with
the correct amount, and honors the owner-tenant gate."""

import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "capi-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import meta_capi  # noqa: E402


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _quoted_ride(c: TestClient) -> dict:
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek, Denver, CO",
            "dropoff": "Union Station, Denver, CO",
            "scheduled_at": "2026-08-14T01:00:00Z",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _patch_recorder(monkeypatch) -> list:
    calls: list = []

    async def _rec(**kwargs):
        calls.append(kwargs)
        return {"sent": False, "simulated": True}

    monkeypatch.setattr(meta_capi, "send_purchase", _rec)
    return calls


def test_authorize_schedules_capi_purchase(monkeypatch):
    calls = _patch_recorder(monkeypatch)
    c = _owner()
    ride = _quoted_ride(c)
    r = c.post(
        "/api/v1/payments",
        json={"ride_id": ride["id"], "source_id": "cnon:card-nonce-ok"},
    )
    assert r.status_code == 201, r.text
    # Starlette runs background tasks before the TestClient returns.
    assert len(calls) == 1, calls
    kw = calls[0]
    assert kw["ride_id"] == ride["id"]
    assert kw["currency"] == "USD"
    assert kw["value"] == round((ride["fare_total"] or 0), 2)


def test_owner_gate_blocks_non_owner_tenant(monkeypatch):
    calls = _patch_recorder(monkeypatch)
    monkeypatch.setenv("OWNER_TENANT_ID", "999999")  # owner tenant is 1 in tests
    get_settings.cache_clear()
    try:
        c = _owner()
        ride = _quoted_ride(c)
        r = c.post(
            "/api/v1/payments",
            json={"ride_id": ride["id"], "source_id": "cnon:card-nonce-ok"},
        )
        assert r.status_code == 201, r.text
        assert calls == []  # gated out — this booking's tenant != owner
    finally:
        get_settings.cache_clear()


if __name__ == "__main__":
    asyncio.run(asyncio.sleep(0))
