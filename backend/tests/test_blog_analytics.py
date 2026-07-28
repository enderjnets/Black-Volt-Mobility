"""What the Analytics tab is handed.

The endpoint used to return each Search Console day WITHOUT its date, so no trend could ever
be drawn, and the tab then used exactly one of the fourteen days it had downloaded. On top of
that every number is legitimately zero — the site has no impressions yet — which read as a
broken tab rather than an honest one. So the engine's own output ships alongside: those
numbers are true today.

Isolated blackvolt_test DB only.
"""
import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import BlogKeyword, BlogPost, SeoSnapshot, Tenant  # noqa: E402
from app.services import blog as blog_service  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _tenant(db) -> int:
    t = Tenant(slug=f"an-{uuid.uuid4().hex[:8]}", name="Analytics Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


async def _gsc_days(db, tid: int, days: list[tuple[str, int, int]]):
    for date, clicks, impressions in days:
        db.add(SeoSnapshot(
            tenant_id=tid, kind="gsc_day", date=date,
            payload={
                "clicks": clicks, "impressions": impressions,
                "ctr": round(clicks / impressions * 100, 2) if impressions else 0.0,
                "top_queries": [
                    {"query": "denver airport car service", "clicks": clicks,
                     "impressions": impressions, "ctr": 1.0, "position": 11.2}
                ] if impressions else [],
            },
        ))
    await db.commit()


async def test_every_day_carries_its_date(db):
    """THE bug: without a date the tab cannot plot anything, so it showed one bare column."""
    tid = await _tenant(db)
    await _gsc_days(db, tid, [("2026-07-24", 1, 10), ("2026-07-25", 2, 20)])
    out = await blog_service.analytics(db, tenant_id=tid)
    assert [d["date"] for d in out["gsc"]] == ["2026-07-24", "2026-07-25"]


async def test_days_come_back_oldest_first_so_a_trend_reads_left_to_right(db):
    tid = await _tenant(db)
    await _gsc_days(db, tid, [("2026-07-26", 3, 30), ("2026-07-24", 1, 10), ("2026-07-25", 2, 20)])
    out = await blog_service.analytics(db, tenant_id=tid)
    assert [d["date"] for d in out["gsc"]] == ["2026-07-24", "2026-07-25", "2026-07-26"]


async def test_all_the_stored_days_are_returned_not_just_the_newest(db):
    tid = await _tenant(db)
    await _gsc_days(db, tid, [(f"2026-07-{d:02d}", 1, 10) for d in range(1, 15)])
    out = await blog_service.analytics(db, tenant_id=tid)
    assert len(out["gsc"]) == 14
    assert out["gsc_totals"] == {"days": 14, "clicks": 14, "impressions": 140, "ctr": 10.0}


async def test_totals_are_zero_without_dividing_by_zero(db):
    """The real production state: fourteen days of nothing."""
    tid = await _tenant(db)
    await _gsc_days(db, tid, [(f"2026-07-{d:02d}", 0, 0) for d in range(1, 15)])
    out = await blog_service.analytics(db, tenant_id=tid)
    assert out["gsc_totals"] == {"days": 14, "clicks": 0, "impressions": 0, "ctr": 0.0}


async def test_a_tenant_with_no_snapshots_gets_an_empty_shape_not_an_error(db):
    tid = await _tenant(db)
    out = await blog_service.analytics(db, tenant_id=tid)
    assert out["gsc"] == []
    assert out["gsc_totals"]["days"] == 0
    assert out["speed"] is None
    assert out["indexing"] is None
    assert out["engine"]["posts"] == {}


async def test_the_engine_block_reports_what_we_actually_produced(db):
    tid = await _tenant(db)
    db.add_all([
        BlogPost(tenant_id=tid, slug=f"p{uuid.uuid4().hex[:6]}", title_en="A", status="published",
                 published_at=dt.datetime(2026, 7, 28, tzinfo=dt.UTC)),
        BlogPost(tenant_id=tid, slug=f"p{uuid.uuid4().hex[:6]}", title_en="B", status="draft"),
        BlogPost(tenant_id=tid, slug=f"p{uuid.uuid4().hex[:6]}", title_en="C", status="scheduled"),
        BlogKeyword(tenant_id=tid, keyword="boulder to den", lang="en", source="gsc",
                    status="planned", score=9.0),
        BlogKeyword(tenant_id=tid, keyword="denver to vail", lang="en", source="llm",
                    status="written", score=2.0),
    ])
    await db.commit()
    out = await blog_service.analytics(db, tenant_id=tid)
    engine = out["engine"]
    assert engine["posts"] == {"published": 1, "draft": 1, "scheduled": 1}
    assert engine["keywords"] == {"planned": 1, "written": 1}
    assert engine["keyword_sources"] == {"gsc": 1, "llm": 1}
    assert engine["next_keyword"] == "boulder to den"
    assert engine["last_published"] is not None


async def test_the_newest_speed_and_indexing_snapshots_are_surfaced(db):
    tid = await _tenant(db)
    db.add_all([
        SeoSnapshot(tenant_id=tid, kind="speed", date="2026-07-27",
                    payload={"method": "self", "summary": {"warnings": 9}}),
        SeoSnapshot(tenant_id=tid, kind="speed", date="2026-07-28",
                    payload={"method": "self", "summary": {"warnings": 1}}),
        SeoSnapshot(tenant_id=tid, kind="indexing", date="2026-07-28",
                    payload={"checked": 1, "indexed": 0, "urls": []}),
    ])
    await db.commit()
    out = await blog_service.analytics(db, tenant_id=tid)
    assert out["speed"]["summary"]["warnings"] == 1  # newest, not the first row found
    assert out["indexing"]["checked"] == 1


async def test_another_tenants_data_never_leaks_in(db):
    mine, other = await _tenant(db), await _tenant(db)
    await _gsc_days(db, other, [("2026-07-24", 99, 999)])
    db.add(BlogPost(tenant_id=other, slug=f"p{uuid.uuid4().hex[:6]}", title_en="X",
                    status="published"))
    await db.commit()
    out = await blog_service.analytics(db, tenant_id=mine)
    assert out["gsc"] == []
    assert out["engine"]["posts"] == {}
