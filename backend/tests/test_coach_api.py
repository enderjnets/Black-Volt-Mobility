"""API tests for the My Stats AI coach. DB-backed; no LLM key → template mode."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "coach-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
# No KIMI/MINIMAX keys → coach falls back to the deterministic template.

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


def test_coach_requires_staff():
    assert client.get("/api/v1/stats/coach").status_code == 401


def test_coach_template_shape_and_real_numbers():
    c = _owner()
    # Log activity where PITCH is clearly the weakest stage (5/100).
    c.post(
        "/api/v1/stats/funnel/log",
        json={"date": "2026-06-09", "conversations": 100, "pitches": 5, "contacts": 5},
    )
    r = c.get("/api/v1/stats/coach?lang=en")
    assert r.status_code == 200, r.text
    b = r.json()
    # No LLM key configured → deterministic template, never an AI hallucination.
    assert b["source"] == "template"
    assert isinstance(b["message"], str) and b["message"].strip()
    ins = b["insight"]
    for k in (
        "focus_stage", "suggested_per_day", "prob_at_least_one",
        "expected_clients", "expected_revenue", "has_earnings",
    ):
        assert k in ins, k
    assert ins["focus_stage"] == "pitch"  # the bottleneck we engineered
    assert 0.0 <= ins["prob_at_least_one"] <= 1.0


def test_coach_mentions_platform_volume():
    c = _owner()
    c.post(
        "/api/v1/stats/funnel/log",
        json={"date": "2026-06-09", "conversations": 80, "pitches": 30, "contacts": 12},
    )
    c.post(
        "/api/v1/stats/platform",
        json={"platform": "uber", "trips": 137, "earnings": 900.0, "online_hours": 30.0},
    )
    # Read the real platform aggregate (rows accumulate across tests) so the
    # assertion tracks the actual number the coach should surface.
    trips = c.get("/api/v1/stats/platform").json()["totals"]["trips"]
    assert trips >= 137
    b = c.get("/api/v1/stats/coach?lang=en").json()
    # The deterministic platform-conversion angle surfaces the real trip count.
    assert str(trips) in b["message"]


def test_coach_spanish_and_refresh():
    c = _owner()
    c.post(
        "/api/v1/stats/funnel/log",
        json={"date": "2026-06-09", "conversations": 40, "pitches": 20, "contacts": 10},
    )
    es = c.get("/api/v1/stats/coach?lang=es").json()
    assert es["source"] == "template" and es["message"].strip()
    # refresh bypasses any cache and still returns a valid card.
    r = c.get("/api/v1/stats/coach?lang=es&refresh=1")
    assert r.status_code == 200, r.text


def test_coach_unknown_locale_falls_back_to_en():
    c = _owner()
    r = c.get("/api/v1/stats/coach?lang=fr")
    assert r.status_code == 200, r.text
    assert r.json()["message"].strip()
