"""Telling Google the sitemap exists.

URL inspection reported "URL is unknown to Google" with `last_crawl: null` for every
published article — Google had never come round at all, which is why fifteen straight days
show zero impressions. Submitting the sitemap is the one part of getting crawled that can be
automated (asking Google to index a specific page cannot: the Indexing API is restricted to
job postings and broadcasts).

Google's client is monkeypatched throughout; no network, no credentials. DB work uses the
isolated blackvolt_test only.
"""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import BlogPost, Tenant  # noqa: E402
from app.services import blog as blog_service  # noqa: E402
from app.services import blog_publish, gsc  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _tenant(db) -> int:
    t = Tenant(slug=f"sm-{uuid.uuid4().hex[:8]}", name="Sitemap Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


async def _connected(db, tid: int):
    cfg = await blog_service.ensure_config(db, tenant_id=tid)
    cfg.gsc_refresh_token = "fake-refresh-token"
    cfg.gsc_site_url = "sc-domain:blackvoltmobility.com"
    await db.commit()


class _HttpError(Exception):
    """Shaped like googleapiclient's HttpError: the status hangs off `resp`."""

    def __init__(self, status: int):
        super().__init__(f"<HttpError {status}>")
        self.resp = type("R", (), {"status": status})()


# ─── Scope ─────────────────────────────────────────────────────────────────────


async def test_we_ask_google_for_write_access():
    """Read-only cannot submit a sitemap. Pinned so nobody narrows it back by habit."""
    assert "https://www.googleapis.com/auth/webmasters" in gsc.SCOPES
    assert "https://www.googleapis.com/auth/webmasters.readonly" not in gsc.SCOPES


async def test_the_default_feedpath_is_our_real_sitemap():
    assert gsc.default_feedpath().endswith("/sitemap.xml")


# ─── Status ────────────────────────────────────────────────────────────────────


async def test_status_without_a_connection_says_so(db):
    tid = await _tenant(db)
    assert await gsc.sitemap_status(db, tenant_id=tid) == {"skipped": "gsc_not_connected"}


async def test_status_reports_never_downloaded(db, monkeypatch):
    """The production smoking gun: registered, but Google has never read it."""
    tid = await _tenant(db)
    await _connected(db, tid)
    monkeypatch.setattr(gsc, "_sitemaps_list", lambda *a: [
        {"path": "https://blackvoltmobility.com/sitemap.xml",
         "lastSubmitted": "2026-07-28T06:00:00Z", "lastDownloaded": None,
         "isPending": True, "warnings": "0", "errors": "0"},
    ])
    out = await gsc.sitemap_status(db, tenant_id=tid)
    assert out["expected"].endswith("/sitemap.xml")
    entry = out["sitemaps"][0]
    assert entry["last_downloaded"] is None
    assert entry["pending"] is True
    assert entry["warnings"] == 0 and entry["errors"] == 0


async def test_no_sitemap_registered_is_an_empty_list_not_an_error(db, monkeypatch):
    tid = await _tenant(db)
    await _connected(db, tid)
    monkeypatch.setattr(gsc, "_sitemaps_list", lambda *a: [])
    out = await gsc.sitemap_status(db, tenant_id=tid)
    assert out["sitemaps"] == []
    assert "skipped" not in out


async def test_an_old_readonly_token_asks_for_a_reconnect_not_an_error(db, monkeypatch):
    """A token minted before we widened the scope can read but not write. "Reconnect once"
    is a different instruction from "something broke", and the owner needs the right one."""
    tid = await _tenant(db)
    await _connected(db, tid)

    def boom(*a):
        raise _HttpError(403)

    monkeypatch.setattr(gsc, "_sitemaps_list", boom)
    assert await gsc.sitemap_status(db, tenant_id=tid) == {"skipped": "needs_reauth"}


async def test_any_other_google_failure_is_reported_as_itself(db, monkeypatch):
    tid = await _tenant(db)
    await _connected(db, tid)

    def boom(*a):
        raise _HttpError(500)

    monkeypatch.setattr(gsc, "_sitemaps_list", boom)
    assert await gsc.sitemap_status(db, tenant_id=tid) == {"skipped": "list_failed"}


# ─── Submit ────────────────────────────────────────────────────────────────────


async def test_submitting_uses_our_sitemap_and_property(db, monkeypatch):
    tid = await _tenant(db)
    await _connected(db, tid)
    seen: dict = {}

    def capture(token, site_url, feedpath):
        seen.update(token=token, site_url=site_url, feedpath=feedpath)

    monkeypatch.setattr(gsc, "_sitemaps_submit", capture)
    out = await gsc.submit_sitemap(db, tenant_id=tid)
    assert out["ok"] is True
    assert seen["site_url"] == "sc-domain:blackvoltmobility.com"
    assert seen["feedpath"].endswith("/sitemap.xml")


async def test_submitting_without_a_connection_says_so(db):
    tid = await _tenant(db)
    assert await gsc.submit_sitemap(db, tenant_id=tid) == {"skipped": "gsc_not_connected"}


async def test_submitting_with_a_readonly_token_asks_for_a_reconnect(db, monkeypatch):
    tid = await _tenant(db)
    await _connected(db, tid)

    def boom(*a):
        raise _HttpError(403)

    monkeypatch.setattr(gsc, "_sitemaps_submit", boom)
    assert await gsc.submit_sitemap(db, tenant_id=tid) == {"skipped": "needs_reauth"}


# ─── Publishing nudges Google ──────────────────────────────────────────────────


async def test_publishing_an_article_resubmits_the_sitemap(db, monkeypatch):
    tid = await _tenant(db)
    await _connected(db, tid)
    calls: list = []
    monkeypatch.setattr(gsc, "_sitemaps_submit", lambda *a: calls.append(a))

    post = BlogPost(tenant_id=tid, slug=f"sm-{uuid.uuid4().hex[:6]}", title_en="T",
                    body_md_en="b", status="scheduled")
    db.add(post)
    await db.commit()
    await db.refresh(post)

    out = await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id)
    assert out["status"] == "published"
    assert len(calls) == 1


async def test_a_failing_sitemap_ping_never_blocks_the_publish(db, monkeypatch):
    """Google being down must not cost the owner a publish.

    Patched at `submit_sitemap`, not at the Google client underneath it: that one already
    swallows its own errors, so patching it proves nothing about the guard in the publisher.
    """
    tid = await _tenant(db)
    await _connected(db, tid)

    async def boom(*a, **kw):
        raise RuntimeError("google is down")

    monkeypatch.setattr(gsc, "submit_sitemap", boom)
    post = BlogPost(tenant_id=tid, slug=f"sm-{uuid.uuid4().hex[:6]}", title_en="T",
                    body_md_en="b", status="scheduled")
    db.add(post)
    await db.commit()
    await db.refresh(post)

    out = await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id)
    assert out["status"] == "published"
    row = await blog_service.get_post(db, tenant_id=tid, post_id=post.id)
    assert row.status == "published"
