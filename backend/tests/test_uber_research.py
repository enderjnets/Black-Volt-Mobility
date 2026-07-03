"""Uber competitive research: formula estimator, scoring, offline run_research."""

import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""
os.environ["PRICING_SCOUT_URL"] = ""
os.environ["PRICING_SCOUT_SECRET"] = ""
os.environ["UBER_BLACK_PER_MILE"] = "5"  # pin so the formula math is deterministic here

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Event, Tenant  # noqa: E402
from app.services import uber_research  # noqa: E402


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db, monkeypatch):
    t = Tenant(slug=f"ev-{uuid.uuid4().hex[:8]}", name="Event Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    monkeypatch.setattr(get_settings(), "OWNER_TENANT_ID", t.id)
    return t.id


def test_estimate_formula_and_minimum():
    # base 15 + 10*5 + 20*0.55 + booking 3 = 79.0
    long = uber_research.estimate_uber_formula(10, 20)
    assert long["black"] == 79.0
    assert long["black_suv"] == round(79.0 * 1.25, 2)
    short = uber_research.estimate_uber_formula(1, 2)
    assert short["black"] == 35.0  # minimum floor


def test_score_prefers_margin_then_affluence():
    high = uber_research._score(margin=0.4, affluence=3, distance_from_base_mi=5)
    low = uber_research._score(margin=0.05, affluence=1, distance_from_base_mi=35)
    assert high > low
    assert 0.0 <= high <= 1.0


@pytest.mark.asyncio
async def test_scrape_uber_unset_returns_empty():
    out = await uber_research.scrape_uber(["Boulder, CO"], "Empower Field", None)
    assert out == {}


@pytest.mark.asyncio
async def test_run_research_offline_produces_table(db, owner):
    ev = Event(
        tenant_id=owner, slug=f"evt-{uuid.uuid4().hex[:8]}", title="Ed Sheeran",
        venue_key="empower_field", venue_name="Empower Field at Mile High",
        venue_address="1701 Bryant St, Denver, CO 80204",
        starts_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=3), status="published",
        event_fee=40, night_fee=25, wait_fee_per_hour=30, est_duration_hours=3,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)

    out = await uber_research.run_research(db, event_id=ev.id)
    assert out is not None
    assert out["method"] == "estimate"  # scout unset → formula
    assert len(out["zones"]) == len(uber_research.TARGET_ZONES)
    z0 = out["zones"][0]
    for k in ("name", "our_round_trip", "uber_black", "score", "method", "margin_pct"):
        assert k in z0
    # Rows are ranked by score descending.
    scores = [z["score"] for z in out["zones"]]
    assert scores == sorted(scores, reverse=True)
    assert out["recommendation"]
    # Persisted on the event.
    await db.refresh(ev)
    assert ev.pricing_research["zones"]


@pytest.mark.asyncio
async def test_run_research_unknown_event(db, owner):
    assert await uber_research.run_research(db, event_id=999999) is None
