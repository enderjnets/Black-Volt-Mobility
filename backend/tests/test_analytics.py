"""Analytics API tests. DB-backed — same auth env as the other API tests so
cookies interoperate."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.analytics import device_from_ua  # noqa: E402

client = TestClient(app)


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def test_device_from_ua():
    assert device_from_ua("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile") == "mobile"
    assert device_from_ua("Mozilla/5.0 (iPad; CPU OS 17_0)") == "tablet"
    assert device_from_ua("Mozilla/5.0 (Macintosh; Intel Mac OS X)") == "desktop"
    assert device_from_ua(None) == "desktop"


def test_track_open_and_records():
    body = {
        "events": [
            {
                "type": "session_start",
                "path": "/book",
                "visitor_id": "vis-test-1",
                "session_id": "ses-test-1",
                "referrer": "https://google.com/",
                "utm_source": "newsletter",
                "device": "mobile",
            },
            {"type": "pageview", "path": "/book", "visitor_id": "vis-test-1", "session_id": "s1"},
            {
                "type": "page_duration",
                "path": "/book",
                "duration_ms": 4200,
                "visitor_id": "vis-test-1",
                "session_id": "ses-test-1",
            },
            {"type": "book_start", "path": "/book", "visitor_id": "vis-test-1", "session_id": "s1"},
        ]
    }
    r = client.post("/api/v1/track", json=body, headers={"CF-IPCountry": "US"})
    assert r.status_code == 202, r.text
    assert r.json() == {"ok": True, "count": 4}


def test_track_empty_is_ok():
    r = client.post("/api/v1/track", json={"events": []})
    assert r.status_code == 202
    assert r.json()["count"] == 0


def test_track_malformed_fails_soft():
    r = client.post(
        "/api/v1/track", content="not json", headers={"Content-Type": "text/plain"}
    )
    assert r.status_code == 202
    assert r.json()["ok"] is False


def test_summary_requires_staff():
    r = client.get("/api/v1/analytics/summary")
    assert r.status_code == 401


def test_summary_aggregates_as_owner():
    # Seed a couple of events first.
    client.post(
        "/api/v1/track",
        json={
            "events": [
                {
                    "type": "session_start",
                    "path": "/",
                    "visitor_id": "v9",
                    "session_id": "s9",
                    "device": "desktop",
                },
                {"type": "pageview", "path": "/", "visitor_id": "v9", "session_id": "s9"},
            ]
        },
        headers={"CF-IPCountry": "US"},
    )
    c = _owner()
    r = c.get("/api/v1/analytics/summary", params={"days": 30})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "totals" in body and body["totals"]["pageviews"] >= 1
    assert "timeseries" in body
    assert "funnel" in body
    assert "top_pages" in body
    assert "devices" in body
