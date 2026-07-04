"""Events API: public landing data + admin moderation (approve/dismiss/edit/scan).

Runs against the dev database. Admin routes require the owner session; public routes
are open. Suggestions/events are seeded under the owner tenant (id 1).
"""
import asyncio
import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["SOCIAL_PUBLISH_VIA_BUFFER"] = "false"
os.environ["SEATGEEK_CLIENT_ID"] = ""
os.environ["TICKETMASTER_API_KEY"] = ""
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Event, EventSuggestion  # noqa: E402


def _owner_tid() -> int:
    return get_settings().OWNER_TENANT_ID or 1


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _run(coro):
    return asyncio.run(coro)


async def _seed_suggestion(**over) -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            defaults = dict(
                tenant_id=_owner_tid(), source="ticketmaster",
                source_id=f"api-{uuid.uuid4().hex[:8]}", title="Ed Sheeran",
                performer="Ed Sheeran", venue_name="Empower Field at Mile High",
                venue_key="empower_field", venue_address="1701 Bryant St, Denver, CO",
                starts_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=45),
                image_url=None, status="suggested",
            )
            defaults.update(over)
            s = EventSuggestion(**defaults)
            db.add(s)
            await db.commit()
            await db.refresh(s)
            return s.id
    finally:
        await eng.dispose()


async def _seed_event(**over) -> str:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            slug = over.pop("slug", f"seed-{uuid.uuid4().hex[:8]}")
            defaults = dict(
                tenant_id=_owner_tid(), slug=slug, title="Seeded Show",
                venue_name="Ball Arena", venue_key="ball_arena",
                starts_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=20),
                status="published",
            )
            defaults.update(over)
            db.add(Event(slug=slug, **{k: v for k, v in defaults.items() if k != "slug"}))
            await db.commit()
            return slug
    finally:
        await eng.dispose()


# ─── Admin auth gate ────────────────────────────────────────────────────────────


def test_admin_routes_require_admin():
    anon = TestClient(app)
    for method, path in [
        ("get", "/api/v1/events/suggestions"),
        ("post", "/api/v1/events/scan"),
        ("get", "/api/v1/events/admin"),
    ]:
        r = getattr(anon, method)(path)
        assert r.status_code in (401, 403), f"{path} -> {r.status_code}"


# ─── Public ─────────────────────────────────────────────────────────────────────


def test_public_lists_only_published_future():
    fut = _run(_seed_event(status="published"))
    draft = _run(_seed_event(status="draft"))
    past = _run(_seed_event(
        status="published", starts_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=2)
    ))
    c = TestClient(app)
    r = c.get("/api/v1/events/public")
    assert r.status_code == 200
    slugs = {e["slug"] for e in r.json()}
    assert fut in slugs
    assert draft not in slugs
    assert past not in slugs


def test_public_detail_404_on_draft_and_ok_on_published():
    pub = _run(_seed_event(status="published"))
    draft = _run(_seed_event(status="draft"))
    c = TestClient(app)
    assert c.get(f"/api/v1/events/public/{draft}").status_code == 404
    assert c.get("/api/v1/events/public/nope-nope").status_code == 404
    r = c.get(f"/api/v1/events/public/{pub}")
    assert r.status_code == 200
    body = r.json()
    assert body["venue_profile"]["dropoff"]
    assert body["flat_price"] == 110
    assert body["passed"] is False
    assert "hero_path" not in body  # internal path not leaked


# ─── Admin moderation ────────────────────────────────────────────────────────────


def test_approve_returns_two_posts_and_publishes():
    sid = _run(_seed_suggestion())
    c = _owner()
    r = c.post(f"/api/v1/events/suggestions/{sid}/approve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "published"
    assert len(body["post_ids"]) == 2
    # Landing is now public.
    slug = body["slug"]
    assert TestClient(app).get(f"/api/v1/events/public/{slug}").status_code == 200
    # Re-approving the same (now approved) suggestion → 404.
    assert c.post(f"/api/v1/events/suggestions/{sid}/approve").status_code == 404


def test_dismiss_removes_from_suggestions():
    sid = _run(_seed_suggestion())
    c = _owner()
    assert c.post(f"/api/v1/events/suggestions/{sid}/dismiss").status_code == 200
    listing = c.get("/api/v1/events/suggestions").json()
    assert all(s["id"] != sid for s in listing)
    assert c.post(f"/api/v1/events/suggestions/{sid}/dismiss").status_code == 404


def test_patch_event_updates_about():
    slug = _run(_seed_event(status="published"))
    c = _owner()
    admin_events = c.get("/api/v1/events/admin").json()
    eid = next(e["id"] for e in admin_events if e["slug"] == slug)
    r = c.patch(f"/api/v1/events/admin/{eid}", json={"about_text": "Edited copy"})
    assert r.status_code == 200
    assert r.json()["about_text"] == "Edited copy"


def test_scan_now_runs():
    c = _owner()
    r = c.post("/api/v1/events/scan")
    assert r.status_code == 200
    assert set(r.json()) >= {"fetched", "kept", "created", "updated", "pruned"}
