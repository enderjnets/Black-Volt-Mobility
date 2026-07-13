"""Volt Blog Autopilot — service tests.

No LLM keys are set, so the writer/keyword LLM loops are empty and fall back to the
deterministic templates (network is never hit; autocomplete is monkeypatched in the one
discovery test). Covers config, keywords, link validation, generation, the hybrid-24h
publish window, public reads, and tenant scoping.
"""
import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import BlogKeyword, BlogPost, Tenant  # noqa: E402
from app.services import blog as blog_service  # noqa: E402
from app.services import (  # noqa: E402
    blog_keywords,
    blog_publish,
    blog_writer,
    gsc,
    site_speed,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _mk_tenant(db) -> int:
    t = Tenant(slug=f"blg-{uuid.uuid4().hex[:8]}", name="Blog Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


def _now():
    return dt.datetime.now(dt.UTC)


# ─── Config ──────────────────────────────────────────────────────────────────────


async def test_ensure_config_defaults_and_idempotent(db):
    tid = await _mk_tenant(db)
    cfg = await blog_service.ensure_config(db, tenant_id=tid)
    assert cfg.embed_token
    assert cfg.languages == ["en", "es"]
    assert cfg.cadence_per_week == 5
    assert cfg.autopublish is True
    again = await blog_service.ensure_config(db, tenant_id=tid)
    assert again.id == cfg.id  # one row per tenant


async def test_update_config_clamps_and_filters(db):
    tid = await _mk_tenant(db)
    out = await blog_service.update_config(
        db, tenant_id=tid,
        patch={
            "cadence_per_week": 99,
            "languages": ["en", "fr"],
            "key_themes": ["  airport  ", ""],
            "autopublish": False,
        },
    )
    assert out["cadence_per_week"] == 14
    assert out["languages"] == ["en"]
    assert out["key_themes"] == ["airport"]
    assert out["autopublish"] is False


# ─── Keywords ────────────────────────────────────────────────────────────────────


async def test_add_keyword_dedupe_and_status(db):
    tid = await _mk_tenant(db)
    a = await blog_service.add_keyword(db, tenant_id=tid, keyword="ride to den", lang="en")
    b = await blog_service.add_keyword(db, tenant_id=tid, keyword="ride to den", lang="en")
    assert a["id"] == b["id"]  # dedup on (tenant, keyword, lang)
    upd = await blog_service.set_keyword_status(
        db, tenant_id=tid, keyword_id=a["id"], status="planned"
    )
    assert upd["status"] == "planned"
    assert await blog_service.set_keyword_status(
        db, tenant_id=tid, keyword_id=a["id"], status="bogus"
    ) is None


# ─── Internal-link validation ────────────────────────────────────────────────────


async def test_filter_internal_links_keeps_only_allowed():
    allowed = {"/", "/book", "/blog/known"}
    links = [
        {"href": "https://evil.com", "text": "external"},
        {"href": "/book", "text": "Book"},
        {"href": "/events/unknown-show", "text": "unknown event"},
        {"href": "/rides/denver-airport", "text": "airport ride"},
        {"href": "/blog/known", "text": "related"},
        {"href": "", "text": "empty"},
    ]
    out = blog_service.filter_internal_links(links, allowed)
    hrefs = {x["href"] for x in out}
    assert "https://evil.com" not in hrefs
    assert "/book" in hrefs
    assert "/events/unknown-show" not in hrefs  # not in allowed
    assert "/rides/denver-airport" in hrefs      # trusted /rides/* prefix
    assert "/blog/known" in hrefs


async def test_allowed_link_paths_includes_published_posts(db):
    tid = await _mk_tenant(db)
    post = BlogPost(
        tenant_id=tid, slug="my-first-post", title_en="T", body_md_en="b",
        status="published", published_at=_now(),
    )
    db.add(post)
    await db.commit()
    allowed = await blog_service.allowed_link_paths(db, tenant_id=tid)
    assert "/book" in allowed
    assert "/blog/my-first-post" in allowed


# ─── Article generation (template fallback, no LLM) ──────────────────────────────


async def test_generate_article_template_bilingual_scheduled(db):
    tid = await _mk_tenant(db)
    post = await blog_writer.generate_article(
        db, tenant_id=tid, keyword_text="airport ride to den"
    )
    assert post is not None
    assert post["status"] == "scheduled"
    assert post["title_en"]
    assert post["title_es"]  # es is in default languages
    assert post["slug"]
    # 24h edit window
    row = await blog_service.get_post(db, tenant_id=tid, post_id=post["id"])
    assert row.publish_at > _now() + dt.timedelta(hours=23)
    assert row.body_md_en
    # only allowed internal links survive
    for link in post["internal_links"]:
        assert link["href"] in {"/", "/book", "/rides", "/events", "/blog"} or link[
            "href"
        ].startswith(("/rides/", "/events/", "/blog/"))


async def test_generate_from_keyword_marks_written(db):
    tid = await _mk_tenant(db)
    kw = BlogKeyword(
        tenant_id=tid, keyword="denver to red rocks car", lang="en",
        source="manual", status="planned", score=5.0,
    )
    db.add(kw)
    await db.commit()
    await db.refresh(kw)
    post = await blog_writer.generate_article(db, tenant_id=tid, keyword_id=kw.id)
    assert post["keyword_id"] == kw.id
    await db.refresh(kw)
    assert kw.status == "written"


# ─── Publish (hybrid 24h window) ─────────────────────────────────────────────────


async def test_publish_due_respects_24h_window(db):
    tid = await _mk_tenant(db)
    await blog_service.ensure_config(db, tenant_id=tid)
    future = BlogPost(
        tenant_id=tid, slug=f"future-{uuid.uuid4().hex[:6]}", title_en="F",
        body_md_en="b", status="scheduled", publish_at=_now() + dt.timedelta(hours=5),
    )
    ready = BlogPost(
        tenant_id=tid, slug=f"ready-{uuid.uuid4().hex[:6]}", title_en="R",
        body_md_en="b", status="scheduled", publish_at=_now() - dt.timedelta(minutes=1),
    )
    db.add_all([future, ready])
    await db.commit()
    out = await blog_publish.publish_due(db, tenant_id=tid)
    assert out["published"] == 1
    await db.refresh(future)
    await db.refresh(ready)
    assert future.status == "scheduled"       # window not elapsed
    assert ready.status == "published"
    assert ready.published_at is not None


async def test_publish_creates_autoshare_draft(db):
    from app.models import SocialPost

    tid = await _mk_tenant(db)
    await blog_service.ensure_config(db, tenant_id=tid)
    post = BlogPost(
        tenant_id=tid, slug=f"share-{uuid.uuid4().hex[:6]}", title_en="Ride to DEN",
        excerpt_en="How to get to the airport in style.", body_md_en="b",
        status="scheduled", publish_at=_now() - dt.timedelta(minutes=1),
    )
    db.add(post)
    await db.commit()
    out = await blog_publish.publish_due(db, tenant_id=tid)
    assert out["published"] == 1
    await db.refresh(post)
    assert post.status == "published"
    # a linked draft social post was created (never auto-posted — draft, owner approves)
    assert post.social_post_id is not None
    sp = await db.get(SocialPost, post.social_post_id)
    assert sp is not None
    assert sp.status == "draft"
    assert sp.tenant_id == tid
    assert "/blog/" in (sp.caption or "")


async def test_publish_due_skips_when_manual(db):
    tid = await _mk_tenant(db)
    await blog_service.update_config(db, tenant_id=tid, patch={"autopublish": False})
    post = BlogPost(
        tenant_id=tid, slug=f"manual-{uuid.uuid4().hex[:6]}", title_en="M",
        body_md_en="b", status="scheduled", publish_at=_now() - dt.timedelta(minutes=1),
    )
    db.add(post)
    await db.commit()
    out = await blog_publish.publish_due(db, tenant_id=tid)
    assert out.get("skipped") == "paused_or_manual"
    await db.refresh(post)
    assert post.status == "scheduled"


# ─── Public reads + localization + scoping ───────────────────────────────────────


async def test_public_reads_only_published_and_localize(db):
    tid = await _mk_tenant(db)
    pub = BlogPost(
        tenant_id=tid, slug="pub-post", title_en="EN title", title_es="ES titulo",
        excerpt_en="en", body_md_en="EN body", body_md_es="ES body",
        status="published", published_at=_now(),
    )
    draft = BlogPost(
        tenant_id=tid, slug="draft-post", title_en="draft", body_md_en="x",
        status="scheduled", publish_at=_now() + dt.timedelta(hours=1),
    )
    # a published post with no ES → ES falls back to EN
    en_only = BlogPost(
        tenant_id=tid, slug="en-only", title_en="Only EN", body_md_en="only en",
        status="published", published_at=_now() - dt.timedelta(days=1),
    )
    db.add_all([pub, draft, en_only])
    await db.commit()

    lst = await blog_service.list_public_posts(db, tenant_id=tid, lang="es")
    slugs = {p["slug"] for p in lst}
    assert "pub-post" in slugs
    assert "draft-post" not in slugs

    es = await blog_service.get_public_post(db, tenant_id=tid, slug="pub-post", lang="es")
    assert es["title"] == "ES titulo"
    assert es["body_md"] == "ES body"

    fallback = await blog_service.get_public_post(db, tenant_id=tid, slug="en-only", lang="es")
    assert fallback["title"] == "Only EN"  # ES missing → EN


async def test_tenant_scoping(db):
    a = await _mk_tenant(db)
    b = await _mk_tenant(db)
    db.add(
        BlogPost(
            tenant_id=a, slug="tenant-a-post", title_en="A", body_md_en="a",
            status="published", published_at=_now(),
        )
    )
    await db.commit()
    a_list = await blog_service.list_public_posts(db, tenant_id=a)
    b_list = await blog_service.list_public_posts(db, tenant_id=b)
    assert any(p["slug"] == "tenant-a-post" for p in a_list)
    assert all(p["slug"] != "tenant-a-post" for p in b_list)


# ─── Writer daily cadence gate ───────────────────────────────────────────────────


async def test_writer_daily_cadence_and_planned(db):
    tid = await _mk_tenant(db)
    # cadence 0 → always skip
    await blog_service.update_config(db, tenant_id=tid, patch={"cadence_per_week": 0})
    out = await blog_writer.run_daily(db, tenant_id=tid)
    assert out.get("skipped") == "cadence_reached"
    # cadence 5 but no planned keyword
    await blog_service.update_config(db, tenant_id=tid, patch={"cadence_per_week": 5})
    out = await blog_writer.run_daily(db, tenant_id=tid)
    assert out.get("skipped") == "no_planned_keyword"
    # add a planned keyword → generates
    kw = BlogKeyword(
        tenant_id=tid, keyword="book premium ev ride denver", lang="en",
        source="llm", status="planned", score=9.0,
    )
    db.add(kw)
    await db.commit()
    out = await blog_writer.run_daily(db, tenant_id=tid)
    assert out.get("generated") is True


# ─── Keyword discovery (network monkeypatched) ───────────────────────────────────


async def test_keyword_discovery_scores_and_promotes(db, monkeypatch):
    tid = await _mk_tenant(db)

    async def fake_autocomplete(seed, lang):
        return ["denver airport car service near me"]

    async def fake_llm(brand, cfg, lang):
        return [{"keyword": "book ride to den airport", "volume": 200, "difficulty": 20}]

    monkeypatch.setattr(blog_keywords, "_autocomplete", fake_autocomplete)
    monkeypatch.setattr(blog_keywords, "_llm_keywords", fake_llm)

    out = await blog_keywords.run_daily(db, tenant_id=tid, promote=2)
    assert out["found"] >= 1
    assert out["promoted"] >= 1
    planned = await blog_service.list_keywords(db, tenant_id=tid, status="planned")
    assert planned
    # high-intent keyword scores above a bland one
    hi = blog_keywords._score("book ride to den airport", "llm", 200, 20)
    lo = blog_keywords._score("colorado", "llm", 200, 20)
    assert hi > lo


# ─── PSI + GSC parsers (F4 integrations) ─────────────────────────────────────────


async def test_parse_psi_extracts_scores_and_opportunities():
    data = {
        "lighthouseResult": {
            "categories": {
                "performance": {"score": 0.92},
                "seo": {"score": 1.0},
                "accessibility": {"score": 0.88},
                "best-practices": {"score": 0.95},
            },
            "audits": {
                "largest-contentful-paint": {"displayValue": "1.8 s", "numericValue": 1800},
                "cumulative-layout-shift": {"displayValue": "0.02", "numericValue": 0.02},
                "total-blocking-time": {"displayValue": "120 ms", "numericValue": 120},
                "first-contentful-paint": {"displayValue": "1.1 s"},
                "uses-webp-images": {
                    "title": "Serve images in next-gen formats",
                    "numericValue": 900,
                    "details": {"type": "opportunity"},
                },
                "tiny-op": {"title": "x", "numericValue": 50, "details": {"type": "opportunity"}},
            },
        }
    }
    out = site_speed.parse_psi(data)
    assert out["performance"] == 92
    assert out["seo"] == 100
    assert out["lcp"] == "1.8 s"
    # opportunities > 100ms only, sorted by savings
    assert out["top_opportunities"] and out["top_opportunities"][0]["savings_ms"] == 900
    assert all(o["savings_ms"] > 100 for o in out["top_opportunities"])


async def test_parse_gsc_summary_and_top_queries():
    rows = [
        {"keys": ["denver airport ride"], "clicks": 30, "impressions": 500,
         "ctr": 0.06, "position": 3.2},
        {"keys": ["red rocks car service"], "clicks": 10, "impressions": 200,
         "ctr": 0.05, "position": 5.1},
    ]
    out = gsc.parse_gsc(rows)
    assert out["clicks"] == 40
    assert out["impressions"] == 700
    assert out["top_queries"][0]["query"] == "denver airport ride"  # sorted by clicks
    assert out["top_queries"][0]["ctr"] == 6.0


async def test_gsc_run_daily_skips_when_not_connected(db):
    tid = await _mk_tenant(db)
    await blog_service.ensure_config(db, tenant_id=tid)
    out = await gsc.run_daily(db, tenant_id=tid)
    assert out.get("skipped") == "gsc_not_connected"


async def test_gsc_authorize_url_has_scope_and_redirect():
    url = gsc.authorize_url("https://app.example.com/cb", "STATE123")
    assert "webmasters.readonly" in url
    assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcb" in url
    assert "state=STATE123" in url
    assert "access_type=offline" in url


# ─── Brand DNA seed/backfill + autofill (follow-up) ──────────────────────────────


async def test_ensure_config_seeds_full_brand_dna(db):
    tid = await _mk_tenant(db)
    cfg = await blog_service.ensure_config(db, tenant_id=tid)
    assert cfg.voice and cfg.audience and cfg.image_style
    assert cfg.key_themes and cfg.avoid_topics


async def test_ensure_config_backfills_blank_existing_row(db):
    from app.models import BlogConfig

    tid = await _mk_tenant(db)
    # simulate an older row created before the fields existed (all blank)
    db.add(BlogConfig(tenant_id=tid, embed_token="tok-" + uuid.uuid4().hex[:8]))
    await db.commit()
    cfg = await blog_service.ensure_config(db, tenant_id=tid)
    assert cfg.voice == blog_service._DEFAULT_VOICE
    assert cfg.audience == blog_service._DEFAULT_AUDIENCE
    assert cfg.image_style == blog_service._DEFAULT_IMAGE_STYLE
    assert cfg.avoid_topics == blog_service._DEFAULT_AVOID
    assert cfg.key_themes == blog_service._DEFAULT_KEY_THEMES


async def test_autofill_config_persists_llm_output(db, monkeypatch):
    from app.services import llm

    tid = await _mk_tenant(db)
    monkeypatch.setattr(llm, "providers", lambda: [("m", "http://x", "key")])

    async def fake_text_complete(**kw):
        return (
            '{"voice": "bold and premium", "audience": "Denver pros", '
            '"key_themes": ["airport", "red rocks"], "avoid_topics": ["politics"], '
            '"image_style": "night EV9 cinematic"}'
        )

    monkeypatch.setattr(llm, "text_complete", fake_text_complete)
    out = await blog_service.autofill_config(db, tenant_id=tid)
    assert out["voice"] == "bold and premium"
    assert out["audience"] == "Denver pros"
    assert out["key_themes"] == ["airport", "red rocks"]
    assert out["image_style"] == "night EV9 cinematic"


async def test_autofill_config_falls_back_when_no_llm(db):
    tid = await _mk_tenant(db)
    # no LLM keys → providers() empty → keeps seeded defaults, no crash
    out = await blog_service.autofill_config(db, tenant_id=tid)
    assert out["voice"] == blog_service._DEFAULT_VOICE


# ─── Site speed keyless (follow-up) ──────────────────────────────────────────────


async def test_site_speed_quota_maps_to_hint(db, monkeypatch):
    tid = await _mk_tenant(db)

    async def fake_fetch(url, key):
        return "quota"

    monkeypatch.setattr(site_speed, "_fetch", fake_fetch)
    out = await site_speed.run_daily(db, tenant_id=tid)
    assert out.get("skipped") == "psi_quota_or_key"


async def test_site_speed_persists_snapshot(db, monkeypatch):
    from app.models import SeoSnapshot

    tid = await _mk_tenant(db)

    async def fake_fetch(url, key):
        return {
            "lighthouseResult": {
                "categories": {"performance": {"score": 0.9}, "seo": {"score": 1.0}},
                "audits": {"largest-contentful-paint": {"displayValue": "1.5 s"}},
            }
        }

    monkeypatch.setattr(site_speed, "_fetch", fake_fetch)
    out = await site_speed.run_daily(db, tenant_id=tid)
    assert out.get("ok") is True
    assert out.get("performance") == 90
    row = (
        await db.execute(
            select(SeoSnapshot).where(SeoSnapshot.tenant_id == tid, SeoSnapshot.kind == "psi")
        )
    ).scalar_one_or_none()
    assert row is not None and row.payload["performance"] == 90


# ─── LLM JSON parsing ────────────────────────────────────────────────────────────


async def test_parse_json_tolerates_raw_newlines_and_fences():
    # MiniMax pretty-prints JSON with literal newlines inside body_md and wraps
    # it in a ```json fence — the strict parser rejected this and dropped every
    # article to the template. The parser must recover title + body.
    raw = (
        "```json\n"
        '{\n'
        '  "title": "Denver Airport Black Car",\n'
        '  "excerpt": "Ride in style.",\n'
        '  "body_md": "## Intro\n\nA premium ride to DEN.\n\n## Why us\n\nAll-electric.",\n'
        '  "faq": [{"q": "How?", "a": "Book online."}],\n'
        '  "internal_links": [{"href": "/book", "text": "Book"}]\n'
        '}\n'
        "```"
    )
    data = blog_writer._parse_json(raw)
    assert data is not None
    assert data["title"] == "Denver Airport Black Car"
    assert "premium ride" in data["body_md"].lower()
    assert data["faq"][0]["q"] == "How?"
