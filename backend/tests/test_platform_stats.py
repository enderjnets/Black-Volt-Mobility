"""API tests for platform-stats import (Uber/Lyft/Co-op screenshots → My Stats)."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"  # extraction returns the deterministic sample

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

# 1x1 PNG.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def test_platform_requires_staff():
    assert client.get("/api/v1/stats/platform").status_code == 401
    assert client.post("/api/v1/stats/platform", json={"platform": "uber"}).status_code == 401
    assert client.post("/api/v1/stats/platform/extract").status_code == 401


def test_extract_simulated_returns_sample():
    c = _owner()
    r = c.post(
        "/api/v1/stats/platform/extract",
        files=[("files", ("uber.png", _PNG, "image/png"))],
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["simulated"] is True
    assert b["fields"]["platform"] == "uber"
    assert b["fields"]["trips"] == 42
    assert b["fields"]["earnings"] == 884.50


def test_extract_rejects_non_image():
    c = _owner()
    r = c.post(
        "/api/v1/stats/platform/extract",
        files=[("files", ("x.txt", b"hello", "text/plain"))],
    )
    assert r.status_code == 400


def test_save_list_and_delete():
    c = _owner()
    # Save a confirmed record.
    r = c.post(
        "/api/v1/stats/platform",
        json={
            "platform": "uber",
            "period_label": "This week",
            "period_end": "2026-06-16",
            "trips": 40,
            "earnings": 800,
            "online_hours": 30,
            "currency": "USD",
        },
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["platform"] == "uber" and r.json()["trips"] == 40

    # Shows up in the summary (window includes today).
    summ = c.get("/api/v1/stats/platform?days=30").json()
    assert summ["totals"]["earnings"] >= 800
    assert summ["totals"]["trips"] >= 40
    assert any(p["platform"] == "uber" for p in summ["by_platform"])
    assert "comparison" in summ and "private" in summ["comparison"]
    assert summ["totals"]["per_trip"] is not None

    # Delete it.
    assert c.delete(f"/api/v1/stats/platform/{sid}").status_code == 204
    assert c.delete(f"/api/v1/stats/platform/{sid}").status_code == 404


def test_save_clamps_unknown_platform_and_negatives():
    c = _owner()
    r = c.post(
        "/api/v1/stats/platform",
        json={"platform": "weirdapp", "trips": 5, "earnings": 100},
    )
    assert r.status_code == 201, r.text
    assert r.json()["platform"] == "other"  # unknown → other
    # Negative earnings rejected by the schema.
    assert c.post("/api/v1/stats/platform", json={"earnings": -5}).status_code == 422


def test_summary_shape_empty_ok():
    c = _owner()
    b = c.get("/api/v1/stats/platform?days=7").json()
    for k in ("days", "totals", "by_platform", "private_revenue", "comparison", "imports"):
        assert k in b, k
