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


# ── staff/dashboard exclusion (deterministic, isolated tenant) ────────────────

import asyncio  # noqa: E402

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models import AnalyticsEvent, Tenant  # noqa: E402
from app.services import analytics  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


async def _seed_excl_tenant() -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            slug = "analytics-excl-test"
            t = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
            if t is None:
                t = Tenant(slug=slug, name="Analytics Excl")
                db.add(t)
                await db.commit()
                await db.refresh(t)
            await db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.tenant_id == t.id))

            def ev(path: str, role: str, vid: str, sid: str) -> AnalyticsEvent:
                return AnalyticsEvent(
                    tenant_id=t.id,
                    event_type="pageview",
                    path=path,
                    role=role,
                    visitor_id=vid,
                    session_id=sid,
                )

            db.add_all(
                [
                    ev("/book", "anon", "v1", "s1"),  # visitor on a public page → counted
                    ev("/book", "anon", "v2", "s2"),
                    ev("/book", "owner", "v3", "s3"),  # staff → excluded by role
                    ev("/dashboard/stats", "anon", "v4", "s4"),  # dashboard → excluded by path
                ]
            )
            await db.commit()
            return t.id
    finally:
        await eng.dispose()


async def _summary_for(tid: int) -> dict:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            return await analytics.summary(db, tenant_id=tid, days=1)
    finally:
        await eng.dispose()


def test_summary_excludes_staff_and_dashboard():
    tid = _run(_seed_excl_tenant())
    s = _run(_summary_for(tid))
    assert s["totals"]["pageviews"] == 2  # only the two anon /book views
    assert s["totals"]["visitors"] == 2
    paths = [p["path"] for p in s["top_pages"]]
    assert paths == ["/book"]
    assert all(not p.startswith("/dashboard") for p in paths)


# ── funnel-by-session + campaign attribution (deterministic, isolated tenant) ──


async def _seed_campaign_tenant() -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            slug = "analytics-campaign-test"
            t = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
            if t is None:
                t = Tenant(slug=slug, name="Analytics Campaign")
                db.add(t)
                await db.commit()
                await db.refresh(t)
            await db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.tenant_id == t.id))

            def ss(sid: str, camp: str | None) -> AnalyticsEvent:
                return AnalyticsEvent(
                    tenant_id=t.id, event_type="session_start", path="/", role="anon",
                    visitor_id=sid, session_id=sid, utm_campaign=camp,
                    utm_source="site" if camp else None,
                )

            def fn(sid: str, etype: str) -> AnalyticsEvent:
                return AnalyticsEvent(
                    tenant_id=t.id, event_type=etype, path="/book", role="anon",
                    visitor_id=sid, session_id=sid,
                )

            db.add_all(
                [
                    ss("s1", "alpha"), ss("s2", "alpha"), ss("s3", "beta"), ss("s4", None),
                    fn("s1", "book_start"), fn("s1", "book_confirmed"),
                    fn("s2", "book_start"),
                    fn("s3", "book_start"),
                    fn("s4", "book_start"),
                ]
            )
            await db.commit()
            return t.id
    finally:
        await eng.dispose()


def test_funnel_by_session_and_campaign_attribution():
    tid = _run(_seed_campaign_tenant())
    s = _run(_summary_for(tid))
    # global funnel = distinct sessions per step
    assert s["funnel"]["book_start"] == 4
    assert s["funnel"]["book_confirmed"] == 1
    # campaigns attributed by session
    by = {c["campaign"]: c for c in s["campaigns"]}
    assert by["alpha"]["starts"] == 2
    assert by["alpha"]["confirmed"] == 1
    assert by["alpha"]["sessions"] == 2
    assert by["beta"]["starts"] == 1 and by["beta"]["confirmed"] == 0
    assert by["(none)"]["starts"] == 1
    # ordered by starts desc → alpha first
    assert s["campaigns"][0]["campaign"] == "alpha"
