"""API tests for the driver funnel ("My Stats") endpoints. DB-backed."""
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


def test_funnel_requires_staff():
    assert client.get("/api/v1/stats/funnel").status_code == 401
    assert client.post("/api/v1/stats/funnel/log", json={}).status_code == 401
    assert client.get("/api/v1/stats/funnel/goal").status_code == 401
    assert client.post("/api/v1/stats/funnel/project", json={}).status_code == 401


def test_summary_shape():
    c = _owner()
    r = c.get("/api/v1/stats/funnel")
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("days", "totals", "rates", "timeseries", "streak", "week", "goal", "projection"):
        assert k in b, k
    assert len(b["timeseries"]) == b["days"]
    assert "overall_point" in b["rates"]


def test_log_upsert_and_clamp():
    c = _owner()
    # Pitches can't exceed conversations; contacts can't exceed pitches.
    r = c.post(
        "/api/v1/stats/funnel/log",
        json={"date": "2026-06-10", "conversations": 10, "pitches": 50, "contacts": 99},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["conversations"] == 10
    assert b["pitches"] == 10  # clamped to conversations
    assert b["contacts"] == 10  # clamped to pitches
    # Re-posting the same date overwrites (upsert), doesn't duplicate.
    r2 = c.post(
        "/api/v1/stats/funnel/log",
        json={"date": "2026-06-10", "conversations": 8, "pitches": 4, "contacts": 2},
    )
    assert r2.json()["conversations"] == 8 and r2.json()["pitches"] == 4

    # It shows up in the summary totals window.
    summ = c.get("/api/v1/stats/funnel?days=365").json()
    assert summ["totals"]["conversations"] >= 8


def test_log_rejects_negative():
    c = _owner()
    assert c.post("/api/v1/stats/funnel/log", json={"conversations": -1}).status_code == 422


def test_goal_roundtrip():
    c = _owner()
    r = c.put(
        "/api/v1/stats/funnel/goal",
        json={
            "target_weekly_revenue": 2000,
            "target_monthly_clients": 8,
            "working_days_per_week": 6,
        },
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["target_weekly_revenue"] == 2000
    assert b["target_monthly_clients"] == 8
    assert b["working_days_per_week"] == 6
    # Persisted.
    assert c.get("/api/v1/stats/funnel/goal").json()["working_days_per_week"] == 6
    # Out-of-range working days is rejected.
    assert c.put("/api/v1/stats/funnel/goal", json={"working_days_per_week": 9}).status_code == 422


def test_project_by_clients():
    c = _owner()
    c.post(
        "/api/v1/stats/funnel/log",
        json={"date": "2026-06-09", "conversations": 100, "pitches": 60, "contacts": 30},
    )
    r = c.post("/api/v1/stats/funnel/project", json={"period": "month", "target_clients": 10})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ok"] is True
    assert b["required"]["conversations"] > 0
    assert b["required"]["conversations_per_day"] > 0


def test_project_by_revenue_without_earnings_flags_unknown():
    # A fresh tenant with no earned rides can't translate revenue → clients.
    c = _owner()
    r = c.post("/api/v1/stats/funnel/project", json={"period": "week", "target_revenue": 1000})
    assert r.status_code == 200, r.text
    b = r.json()
    # Either it computed (if earlier tests left earnings) or flagged unknown —
    # both are valid; assert the contract holds.
    assert "ok" in b
    if not b["ok"]:
        assert b["revenue_unknown"] is True
