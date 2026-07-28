"""Site speed, measured by us instead of by PageSpeed Insights.

PSI without an API key is not "rate limited at low volume" — every keyless caller shares one
Google project whose daily quota is permanently spent, so the Speed tab never held a single
data point in its life. These tests pin the replacement: real numbers, no key, and a failing
page recorded rather than thrown away.

Parsing tests are pure; the end-to-end one runs against httpx.MockTransport, never the
network. DB work uses the isolated blackvolt_test only.
"""
import gzip
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import BlogPost, SeoSnapshot, Tenant  # noqa: E402
from app.services import site_speed  # noqa: E402

# ─── Pure parsing ──────────────────────────────────────────────────────────────


def test_a_blocking_script_and_stylesheet_are_counted():
    html = """
    <html><head>
      <script src="/a.js"></script>
      <link rel="stylesheet" href="/a.css">
    </head><body><script src="/late.js"></script></body></html>
    """
    assert site_speed.count_blocking(html) == {"scripts": 1, "styles": 1}


def test_defer_and_async_do_not_block():
    html = '<html><head><script src="/a.js" defer></script>' \
           '<script src="/b.js" async></script></head></html>'
    assert site_speed.count_blocking(html)["scripts"] == 0


def test_json_ld_is_not_treated_as_a_blocking_script():
    """We emit BlogPosting + FAQPage on every article; penalising that would be backwards."""
    html = ('<html><head><script type="application/ld+json" src="/x.json"></script>'
            '</head></html>')
    assert site_speed.count_blocking(html)["scripts"] == 0


def test_an_inline_script_is_not_a_round_trip():
    html = '<html><head><script>console.log(1)</script></head></html>'
    assert site_speed.count_blocking(html)["scripts"] == 0


def test_a_preload_link_is_not_a_stylesheet():
    html = '<html><head><link rel="preload" as="font" href="/f.woff2"></head></html>'
    assert site_speed.count_blocking(html)["styles"] == 0


def test_only_the_head_counts():
    html = '<html><head></head><body><link rel="stylesheet" href="/late.css"></body></html>'
    assert site_speed.count_blocking(html) == {"scripts": 0, "styles": 0}


def test_a_page_with_no_head_does_not_explode():
    assert site_speed.count_blocking("just text") == {"scripts": 0, "styles": 0}


def test_image_urls_are_absolute_deduped_and_skip_data_uris():
    html = ('<img src="/a.png"><img src="/a.png">'
            '<img src="https://cdn.example.com/b.jpg">'
            '<img src="data:image/gif;base64,R0lGOD">')
    out = site_speed.image_urls(html, "https://site.test/blog")
    assert out == ["https://site.test/a.png", "https://cdn.example.com/b.jpg"]


# ─── Verdicts ──────────────────────────────────────────────────────────────────


def test_a_healthy_page_is_all_ok():
    v = site_speed.verdict({
        "status": 200, "ttfb_ms": 120, "total_ms": 400, "html_kb": 40,
        "compressed": True, "blocking_scripts": 0, "blocking_styles": 1, "images_kb": 200,
    })
    assert set(v.values()) == {"ok"}


def test_each_threshold_flags_on_its_own():
    base = {
        "status": 200, "ttfb_ms": 10, "total_ms": 10, "html_kb": 1,
        "compressed": True, "blocking_scripts": 0, "blocking_styles": 0, "images_kb": 0,
    }
    def over(field: str, limit: int) -> str:
        return site_speed.verdict({**base, field: limit + 1})[field]

    assert over("ttfb_ms", site_speed.TTFB_WARN_MS) == "warn"
    assert over("total_ms", site_speed.TOTAL_WARN_MS) == "warn"
    assert over("html_kb", site_speed.HTML_WARN_KB) == "warn"
    assert over("images_kb", site_speed.IMAGES_WARN_KB) == "warn"
    assert site_speed.verdict({**base, "compressed": False})["compressed"] == "warn"
    assert site_speed.verdict({**base, "status": 500})["status"] == "warn"
    busted = {**base, "blocking_scripts": site_speed.BLOCKING_WARN, "blocking_styles": 1}
    assert site_speed.verdict(busted)["blocking"] == "warn"


def test_a_page_that_never_answered_is_all_warn_not_all_ok():
    """A timeout must not read as a clean bill of health."""
    v = site_speed.verdict({"error": "timeout"})
    assert v["status"] == "warn"
    assert v["compressed"] == "warn"


# ─── End to end, no network ────────────────────────────────────────────────────

_HTML = (
    "<html><head><script src='/a.js'></script><link rel='stylesheet' href='/a.css'>"
    "</head><body><img src='/hero.jpg'>" + ("<p>filler copy</p>" * 300) + "</body></html>"
).encode()
# Served gzipped, like the real site, so the decode path is exercised for real.
_GZIPPED = gzip.compress(_HTML)


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "HEAD":
        return httpx.Response(200, headers={"content-length": "51200"})
    if request.url.path == "/book":
        return httpx.Response(500, content=b"nope")
    return httpx.Response(200, content=_GZIPPED, headers={"content-encoding": "gzip"})


@pytest.fixture
def mocked_http(monkeypatch):
    real = httpx.AsyncClient

    def make(**kwargs):
        kwargs.pop("transport", None)
        return real(transport=httpx.MockTransport(_handler), **kwargs)

    monkeypatch.setattr(site_speed.httpx, "AsyncClient", make)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _tenant(db) -> int:
    t = Tenant(slug=f"spd-{uuid.uuid4().hex[:8]}", name="Speed Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


async def test_run_daily_measures_and_persists(db, mocked_http):
    tid = await _tenant(db)
    out = await site_speed.run_daily(db, tenant_id=tid)
    assert out["ok"] is True
    assert out["pages"] == 3  # /, /blog, /book — no published post yet

    row = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tid, SeoSnapshot.kind == "speed"
            )
        )
    ).scalar_one()
    payload = row.payload
    assert payload["method"] == "self"  # never to be mistaken for Lighthouse
    home = next(p for p in payload["pages"] if p["path"] == "/")
    assert home["status"] == 200
    assert home["compressed"] is True
    assert home["blocking_scripts"] == 1 and home["blocking_styles"] == 1
    assert home["images_kb"] == 50  # one 51200-byte hero
    # html_kb is the decoded document; `compressed` separately says it travelled gzipped.
    assert home["html_kb"] == round(len(_HTML) / 1024)
    assert home["ttfb_ms"] >= 0 and home["total_ms"] >= home["ttfb_ms"]


async def test_a_failing_page_is_recorded_not_dropped(db, mocked_http):
    tid = await _tenant(db)
    await site_speed.run_daily(db, tenant_id=tid)
    row = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tid, SeoSnapshot.kind == "speed"
            )
        )
    ).scalar_one()
    book = next(p for p in row.payload["pages"] if p["path"] == "/book")
    assert book["status"] == 500
    assert book["verdict"]["status"] == "warn"
    assert row.payload["summary"]["warnings"] >= 1


async def test_the_newest_published_article_is_measured_too(db, mocked_http):
    tid = await _tenant(db)
    db.add(BlogPost(
        tenant_id=tid, slug="denver-to-vail", title_en="T", body_md_en="b",
        status="published",
    ))
    await db.commit()
    out = await site_speed.run_daily(db, tenant_id=tid)
    assert out["pages"] == 4
    row = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tid, SeoSnapshot.kind == "speed"
            )
        )
    ).scalar_one()
    assert any(p["path"] == "/blog/denver-to-vail" for p in row.payload["pages"])


async def test_running_twice_the_same_day_updates_one_row(db, mocked_http):
    tid = await _tenant(db)
    await site_speed.run_daily(db, tenant_id=tid)
    await site_speed.run_daily(db, tenant_id=tid)
    rows = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tid, SeoSnapshot.kind == "speed"
            )
        )
    ).scalars().all()
    assert len(rows) == 1
