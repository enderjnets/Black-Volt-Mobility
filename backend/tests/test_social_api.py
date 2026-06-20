"""API tests for the social module. DB-backed; simulated; no LLM key → template."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "social-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["SOCIAL_PUBLISH_VIA_BUFFER"] = "false"
os.environ["BUFFER_API_KEY"] = ""
os.environ["BUFFER_ORG_ID"] = ""
# Force the deterministic template path (no real Kimi/MiniMax call).
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import auth as A  # noqa: E402

client = TestClient(app)


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _driver():
    """A non-admin driver session (owner of some other tenant)."""
    c = TestClient(app)
    c.cookies.set(
        A.COOKIE_NAME, A.make_token(role=A.ROLE_DRIVER, tenant_id=999999, email="driver@x.com")
    )
    return c


def test_social_requires_admin():
    # Anonymous → 401.
    assert client.get("/api/v1/social/posts").status_code == 401
    assert client.post("/api/v1/social/posts/generate", json={"topic": "x"}).status_code == 401
    # A regular (non-admin) driver → 403: the whole module is admin-only.
    d = _driver()
    assert d.get("/api/v1/social/posts").status_code == 403
    assert d.get("/api/v1/social/inbox").status_code == 403
    assert d.get("/api/v1/social/accounts").status_code == 403
    assert d.get("/api/v1/social/analytics").status_code == 403
    assert d.post("/api/v1/social/posts/generate", json={"topic": "x"}).status_code == 403


def test_generate_creates_draft():
    c = _owner()
    r = c.post("/api/v1/social/posts/generate", json={"topic": "EV9 airport luxury", "lang": "en"})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "draft"
    assert b["source"] == "template"
    assert b["script"] and b["caption"] and b["hashtags"]
    assert b["targets"] == ["instagram", "facebook"]


def test_full_pipeline_render_approve_publish():
    c = _owner()
    pid = c.post("/api/v1/social/posts/generate", json={"topic": "sunset ride"}).json()["id"]

    # Approve before render → 409.
    assert c.post(f"/api/v1/social/posts/{pid}/approve", json={}).status_code == 409

    rendered = c.post(f"/api/v1/social/posts/{pid}/render").json()
    assert rendered["status"] == "rendered" and rendered["simulated_render"] is True

    approved = c.post(f"/api/v1/social/posts/{pid}/approve", json={}).json()
    assert approved["status"] == "approved"

    published = c.post(f"/api/v1/social/posts/{pid}/publish").json()
    assert published["status"] == "published"
    assert "instagram" in published["external_ids"]


def test_schedule_sets_scheduled_status():
    c = _owner()
    pid = c.post("/api/v1/social/posts/generate", json={"topic": "morning"}).json()["id"]
    c.post(f"/api/v1/social/posts/{pid}/render")
    r = c.post(
        f"/api/v1/social/posts/{pid}/approve",
        json={"scheduled_at": "2030-01-01T12:00:00+00:00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"
    assert r.json()["scheduled_at"].startswith("2030-01-01")


def test_reject_returns_to_draft():
    c = _owner()
    pid = c.post("/api/v1/social/posts/generate", json={"topic": "x"}).json()["id"]
    c.post(f"/api/v1/social/posts/{pid}/render")
    c.post(f"/api/v1/social/posts/{pid}/approve", json={})
    r = c.post(f"/api/v1/social/posts/{pid}/reject").json()
    assert r["status"] == "draft" and r["scheduled_at"] is None


def test_update_and_list_filter():
    c = _owner()
    pid = c.post("/api/v1/social/posts/generate", json={"topic": "x"}).json()["id"]
    upd = c.patch(f"/api/v1/social/posts/{pid}", json={"caption": "edited caption"}).json()
    assert upd["caption"] == "edited caption"
    drafts = c.get("/api/v1/social/posts?status=draft").json()
    assert any(p["id"] == pid for p in drafts)


def test_delete_post():
    c = _owner()
    pid = c.post("/api/v1/social/posts/generate", json={"topic": "x"}).json()["id"]
    assert c.delete(f"/api/v1/social/posts/{pid}").status_code == 204
    assert c.delete(f"/api/v1/social/posts/{pid}").status_code == 404


def test_inbox_seeds_demo_and_drafts_reply():
    c = _owner()
    inbox = c.get("/api/v1/social/inbox").json()
    assert len(inbox) >= 1  # simulated mode seeds demo comments
    iid = inbox[0]["id"]
    drafted = c.post(f"/api/v1/social/inbox/{iid}/draft").json()
    assert drafted["source"] == "template"
    assert drafted["ai_draft"] and drafted["reply_status"] == "drafted"
    # Approve + send (optional owner edit).
    sent = c.post(f"/api/v1/social/inbox/{iid}/reply", json={"text": "Thanks! DM us."}).json()
    assert sent["reply_status"] == "sent" and sent["ai_draft"] == "Thanks! DM us."


def test_accounts_lists_all_platforms_disconnected():
    c = _owner()
    accts = c.get("/api/v1/social/accounts").json()
    platforms = {a["platform"] for a in accts}
    assert platforms == {"instagram", "facebook", "tiktok"}
    assert all(a["connected"] is False for a in accts)
    # Tokens are never serialized.
    assert all("access_token" not in a for a in accts)


def test_analytics_shape():
    c = _owner()
    b = c.get("/api/v1/social/analytics").json()
    for k in ("posts_total", "posts_published", "by_status", "views", "pending_replies"):
        assert k in b, k


def test_render_webhook_rejects_unsigned():
    # No signing key configured in tests → every callback is refused.
    r = client.post("/api/v1/social/webhooks/render", json={"post_id": 1})
    assert r.status_code == 403
