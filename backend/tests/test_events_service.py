"""Approval pipeline + admin/public event service."""

import base64
import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["SOCIAL_PUBLISH_VIA_BUFFER"] = "false"
os.environ["SEATGEEK_CLIENT_ID"] = ""
os.environ["TICKETMASTER_API_KEY"] = ""
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Event, EventSuggestion, SocialPost, Tenant  # noqa: E402
from app.services import events  # noqa: E402

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _mk_tenant(db) -> int:
    t = Tenant(slug=f"ev-{uuid.uuid4().hex[:8]}", name="Event Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


@pytest_asyncio.fixture
async def owner(db, monkeypatch):
    """A tenant registered as the events owner (public/archive queries resolve to it)."""
    tid = await _mk_tenant(db)
    monkeypatch.setattr(get_settings(), "OWNER_TENANT_ID", tid)
    return tid


async def _mk_suggestion(db, tid, **over) -> EventSuggestion:
    defaults = dict(
        tenant_id=tid, source="ticketmaster", source_id=f"s-{uuid.uuid4().hex[:8]}",
        title="Ed Sheeran", performer="Ed Sheeran",
        venue_name="Empower Field at Mile High", venue_key="empower_field",
        venue_address="1701 Bryant St, Denver, CO",
        starts_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=40),
        image_url="https://img/ed.jpg", status="suggested",
    )
    defaults.update(over)
    s = EventSuggestion(**defaults)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest.fixture(autouse=True)
def _hero(monkeypatch):
    async def _fake_download(url):
        return (_PNG, "png")
    monkeypatch.setattr(events, "_download_image", _fake_download)


@pytest.mark.asyncio
async def test_approve_creates_published_event_and_two_draft_posts(db):
    tid = await _mk_tenant(db)
    s = await _mk_suggestion(db, tid)
    out = await events.approve_suggestion(db, tenant_id=tid, suggestion_id=s.id)
    assert out is not None
    assert out["status"] == "published"
    assert out["slug"].startswith("ed-sheeran-empower-field")
    assert out["hero_path"] and out["hero_path"].endswith(".png")
    assert out["about_text"] and len(out["about_text"]) > 20
    assert len(out["post_ids"]) == 2
    assert out["posts_error"] is None

    await db.refresh(s)
    assert s.status == "approved"

    posts = (
        await db.execute(select(SocialPost).where(SocialPost.tenant_id == tid))
    ).scalars().all()
    kinds = sorted(p.media_kind for p in posts)
    assert kinds == ["image", "video"]


@pytest.mark.asyncio
async def test_approve_slug_collision_gets_suffix(db):
    tid = await _mk_tenant(db)
    day = dt.datetime.now(dt.UTC) + dt.timedelta(days=50)
    s1 = await _mk_suggestion(db, tid, starts_at=day)
    s2 = await _mk_suggestion(db, tid, starts_at=day)
    o1 = await events.approve_suggestion(db, tenant_id=tid, suggestion_id=s1.id)
    o2 = await events.approve_suggestion(db, tenant_id=tid, suggestion_id=s2.id)
    assert o1["slug"] != o2["slug"]
    assert o1["slug"].startswith("ed-sheeran-empower-field")
    assert o2["slug"].startswith("ed-sheeran-empower-field")


@pytest.mark.asyncio
async def test_approve_survives_hero_download_failure(db, monkeypatch):
    # _download_image returns None on any failure (its contract) → the landing still
    # publishes, just without a hero image.
    async def _none(url):
        return None
    monkeypatch.setattr(events, "_download_image", _none)
    tid = await _mk_tenant(db)
    s = await _mk_suggestion(db, tid)
    out = await events.approve_suggestion(db, tenant_id=tid, suggestion_id=s.id)
    assert out is not None and out["status"] == "published"
    assert out["hero_path"] is None


@pytest.mark.asyncio
async def test_dismiss(db):
    tid = await _mk_tenant(db)
    s = await _mk_suggestion(db, tid)
    assert await events.dismiss_suggestion(db, tenant_id=tid, suggestion_id=s.id) is True
    await db.refresh(s)
    assert s.status == "dismissed"
    # Not found → False
    assert await events.dismiss_suggestion(db, tenant_id=tid, suggestion_id=999999) is False


@pytest.mark.asyncio
async def test_archive_past_events(db, owner):
    tid = owner
    past = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    ev = Event(tenant_id=tid, slug=f"past-{uuid.uuid4().hex[:6]}", title="Past",
               venue_name="Ball Arena", venue_key="ball_arena", starts_at=past,
               status="published")
    db.add(ev)
    await db.commit()
    n = await events.archive_past_events(db)
    assert n >= 1
    await db.refresh(ev)
    assert ev.status == "archived"


@pytest.mark.asyncio
async def test_public_endpoints_shape(db, owner):
    tid = owner
    s = await _mk_suggestion(db, tid)
    out = await events.approve_suggestion(db, tenant_id=tid, suggestion_id=s.id)
    slug = out["slug"]

    pub = await events.list_public_events(db)
    assert any(e["slug"] == slug for e in pub)

    detail = await events.get_public_event(db, slug=slug)
    assert detail is not None
    assert detail["venue_profile"]["dropoff"]
    assert detail["flat_price"] == 110
    assert detail["passed"] is False

    # Draft event → hidden from public detail.
    draft = Event(tenant_id=tid, slug=f"draft-{uuid.uuid4().hex[:6]}", title="D",
                  venue_name="V", starts_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=5),
                  status="draft")
    db.add(draft)
    await db.commit()
    assert await events.get_public_event(db, slug=draft.slug) is None
    assert await events.get_public_event(db, slug="does-not-exist") is None


@pytest.mark.asyncio
async def test_update_event_and_generate_post(db, owner):
    tid = owner
    s = await _mk_suggestion(db, tid)
    out = await events.approve_suggestion(db, tenant_id=tid, suggestion_id=s.id)
    eid = out["id"]

    upd = await events.update_event(
        db, tenant_id=tid, event_id=eid,
        patch={"about_text": "Custom copy", "status": "draft", "bogus": "x"},
    )
    assert upd["about_text"] == "Custom copy" and upd["status"] == "draft"

    # Draft is now hidden from public.
    assert await events.get_public_event(db, slug=out["slug"]) is None

    gen = await events.generate_event_post(db, tenant_id=tid, event_id=eid, kind="video")
    assert "post_id" in gen and gen["kind"] == "video"
    assert await events.generate_event_post(db, tenant_id=tid, event_id=99999, kind="video") == {
        "error": "not_found"
    }


@pytest.mark.asyncio
async def test_scan_job_is_safe_without_key():
    # With no SeatGeek/Ticketmaster key the daily job must run to completion (no-op),
    # never raising — a keyless deployment stays healthy.
    from app.services import scheduler
    await scheduler._events_scan_job()


@pytest.mark.asyncio
async def test_passed_stays_false_during_show_and_grace(db, owner):
    # Regression: an event that just started (or ended minutes ago) must NOT be marked
    # passed — the post-show pickup CTA has to stay live through the archive grace window.
    tid = owner
    now = dt.datetime.now(dt.UTC)
    during = Event(tenant_id=tid, slug=f"during-{uuid.uuid4().hex[:6]}", title="During",
                   venue_name="Ball Arena", venue_key="ball_arena",
                   starts_at=now - dt.timedelta(minutes=30), status="published")
    old = Event(tenant_id=tid, slug=f"old-{uuid.uuid4().hex[:6]}", title="Old",
                venue_name="Ball Arena", venue_key="ball_arena",
                starts_at=now - dt.timedelta(hours=8), status="published")
    db.add_all([during, old])
    await db.commit()
    d1 = await events.get_public_event(db, slug=during.slug)
    d2 = await events.get_public_event(db, slug=old.slug)
    assert d1["passed"] is False  # show in progress → CTA still live
    assert d2["passed"] is True   # well past the 6h grace → retired


@pytest.mark.asyncio
async def test_public_queries_are_tenant_scoped(db, owner, monkeypatch):
    # An event published under a DIFFERENT tenant must never surface on the owner's
    # public surfaces (list + detail).
    other = await _mk_tenant(db)
    fut = dt.datetime.now(dt.UTC) + dt.timedelta(days=10)
    foreign = Event(tenant_id=other, slug=f"foreign-{uuid.uuid4().hex[:6]}", title="Foreign",
                    venue_name="V", starts_at=fut, status="published")
    db.add(foreign)
    await db.commit()
    pub = await events.list_public_events(db)
    assert all(e["slug"] != foreign.slug for e in pub)
    assert await events.get_public_event(db, slug=foreign.slug) is None
