"""Event-pricing API: admin gating on the new pricing-preview / research endpoints."""

import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_pricing_preview_requires_admin():
    r = client.get("/api/v1/events/admin/1/pricing-preview")
    assert r.status_code in (401, 403), r.text


def test_research_requires_admin():
    r = client.post("/api/v1/events/admin/1/research")
    assert r.status_code in (401, 403), r.text
