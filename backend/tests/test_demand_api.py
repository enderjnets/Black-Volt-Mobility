"""API tests for the "Where to wait" demand planner (import, log, week)."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"
os.environ["DEMAND_ENABLED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def test_settings_defaults():
    s = get_settings()
    assert s.DEMAND_ENABLED is True  # set by this module's env
    assert s.DEMAND_BRIDGE_FARE_DEFAULT == 35.0
    assert s.DEMAND_RECOMPUTE_MIN == 15
    assert s.DEN_LOT_RADIUS_M == 400


def test_me_exposes_demand_feature_flag():
    c = _owner()
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["features"] == {"demand": True}
