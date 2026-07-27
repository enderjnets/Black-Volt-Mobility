"""Keyword discovery must prefer what people really searched over what a model imagined.

The module docstring claimed Search Console was source #1 and the code never queried it, so
all 40 keywords in production came from the LLM — with invented monthly volumes that then
ranked the entire content plan. These tests pin the fix: real impressions win, and an LLM
keyword no longer carries a fabricated demand figure.

Isolated blackvolt_test DB only.
"""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import BlogKeyword, SeoSnapshot, Tenant  # noqa: E402
from app.services import blog_keywords  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _tenant(db) -> int:
    t = Tenant(slug=f"kwg-{uuid.uuid4().hex[:8]}", name="Keyword Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


async def _snapshot(db, tenant_id: int, queries: list[dict], *, date: str = "2026-07-26"):
    db.add(
        SeoSnapshot(
            tenant_id=tenant_id, kind="gsc_day", date=date,
            payload={"clicks": 3, "impressions": 200, "ctr": 1.5, "top_queries": queries},
        )
    )
    await db.commit()


async def test_no_snapshot_means_no_gsc_keywords(db):
    tid = await _tenant(db)
    assert await blog_keywords._gsc_keywords(db, tenant_id=tid) == []


async def test_real_queries_become_keywords(db):
    tid = await _tenant(db)
    await _snapshot(db, tid, [
        {"query": "denver airport car service", "clicks": 2, "impressions": 40,
         "ctr": 5.0, "position": 11.2},
    ])
    out = await blog_keywords._gsc_keywords(db, tenant_id=tid)
    assert len(out) == 1
    kw = out[0]
    assert kw["keyword"] == "denver airport car service"
    assert kw["lang"] == "en"
    # 40 impressions over the 3-day window, scaled to a monthly figure.
    assert kw["volume"] == 400
    assert kw["difficulty"] == pytest.approx(11.2)


async def test_a_spanish_query_is_filed_as_spanish(db):
    tid = await _tenant(db)
    await _snapshot(db, tid, [
        {"query": "transporte al aeropuerto de denver", "clicks": 0, "impressions": 12,
         "ctr": 0.0, "position": 22.0},
    ])
    out = await blog_keywords._gsc_keywords(db, tenant_id=tid)
    assert out[0]["lang"] == "es"


async def test_queries_with_no_impressions_are_dropped(db):
    tid = await _tenant(db)
    await _snapshot(db, tid, [
        {"query": "ghost query", "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 90.0},
        {"query": "boulder to den airport", "clicks": 1, "impressions": 9, "ctr": 11.0,
         "position": 8.0},
    ])
    out = await blog_keywords._gsc_keywords(db, tenant_id=tid)
    assert [k["keyword"] for k in out] == ["boulder to den airport"]


async def test_only_the_newest_snapshot_is_used(db):
    tid = await _tenant(db)
    await _snapshot(db, tid, [
        {"query": "old query", "clicks": 0, "impressions": 5, "ctr": 0.0, "position": 40.0},
    ], date="2026-07-01")
    await _snapshot(db, tid, [
        {"query": "fresh query", "clicks": 0, "impressions": 5, "ctr": 0.0, "position": 40.0},
    ], date="2026-07-26")
    out = await blog_keywords._gsc_keywords(db, tenant_id=tid)
    assert [k["keyword"] for k in out] == ["fresh query"]


async def test_a_measured_keyword_outranks_an_imagined_one(db):
    """The whole point. Same intent signals, but one of them is real."""
    real = blog_keywords._score("denver airport car service", "gsc", 400, 11.2)
    imagined = blog_keywords._score("denver airport car service", "llm", None, 35.0)
    assert real > imagined


async def test_discovery_persists_gsc_queries_with_the_gsc_source(db):
    tid = await _tenant(db)
    await _snapshot(db, tid, [
        {"query": "private ride to den airport", "clicks": 1, "impressions": 30,
         "ctr": 3.0, "position": 14.0},
    ])
    out = await blog_keywords.run_daily(db, tenant_id=tid, promote=1)
    assert out["found"] >= 1
    row = (
        await db.execute(
            select(BlogKeyword).where(
                BlogKeyword.tenant_id == tid,
                BlogKeyword.keyword == "private ride to den airport",
            )
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.source == "gsc"
    assert row.volume_est == 300
