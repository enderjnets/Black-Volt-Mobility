"""Scanner: watchlist/score filter, upsert dedup, prune, distance, Ticketmaster."""

import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"
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

from app.models import EventSuggestion, Tenant  # noqa: E402
from app.services import events_scan  # noqa: E402


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db, monkeypatch):
    """Create a tenant and make it the owner tenant for run_scan."""
    t = Tenant(slug=f"own-{uuid.uuid4().hex[:8]}", name="Owner")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    monkeypatch.setattr(get_settings(), "OWNER_TENANT_ID", t.id)
    return t.id


def _sg(id_, title, venue, score, days_ahead=30, lat=39.74, lng=-105.02, performer=None):
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days_ahead)
    return {
        "id": id_,
        "title": title,
        "score": score,
        "url": f"https://seatgeek.com/e/{id_}",
        "datetime_utc": when.strftime("%Y-%m-%dT%H:%M:%S"),
        "venue": {
            "name": venue,
            "address": "123 St",
            "extended_address": "Denver, CO",
            "location": {"lat": lat, "lon": lng},
        },
        "performers": [{"name": performer or title, "image": "https://img/x.jpg"}],
    }


def _fake_sg(events):
    async def _f():
        return list(events)
    return _f


async def _count(db, tid):
    rows = (await db.execute(select(EventSuggestion).where(EventSuggestion.tenant_id == tid))).scalars().all()
    return rows


@pytest.mark.asyncio
async def test_scan_keeps_watchlist_and_big_scores_only(db, owner, monkeypatch):
    monkeypatch.setattr(events_scan, "_fetch_seatgeek", _fake_sg([
        _sg("1", "Ed Sheeran", "Empower Field at Mile High", 0.9),
        _sg("2", "Small Club Show", "Larimer Lounge", 0.3),
        _sg("3", "Huge Fest", "Civic Center Park", 0.8),
    ]))
    out = await events_scan.run_scan(db)
    assert out["kept"] == 2 and out["created"] == 2  # watchlist + big score; club dropped
    rows = await _count(db, owner)
    titles = {r.title for r in rows}
    assert titles == {"Ed Sheeran", "Huge Fest"}


@pytest.mark.asyncio
async def test_scan_upsert_updates_not_duplicates_and_respects_dismissed(db, owner, monkeypatch):
    monkeypatch.setattr(events_scan, "_fetch_seatgeek", _fake_sg([
        _sg("10", "Ed Sheeran", "Empower Field at Mile High", 0.9),
        _sg("11", "Metallica", "Ball Arena", 0.85),
    ]))
    first = await events_scan.run_scan(db)
    assert first["created"] == 2

    # Dismiss one, then rescan with an updated score for it.
    row = (await db.execute(select(EventSuggestion).where(
        EventSuggestion.source_id == "10"))).scalar_one()
    row.status = "dismissed"
    await db.commit()

    monkeypatch.setattr(events_scan, "_fetch_seatgeek", _fake_sg([
        _sg("10", "Ed Sheeran", "Empower Field at Mile High", 0.99),
        _sg("11", "Metallica", "Ball Arena", 0.85),
    ]))
    second = await events_scan.run_scan(db)
    assert second["created"] == 0  # no duplicates
    # Dismissed row untouched; the suggested one may update.
    dismissed = (await db.execute(select(EventSuggestion).where(
        EventSuggestion.source_id == "10"))).scalar_one()
    assert dismissed.status == "dismissed" and dismissed.score == 0.9


@pytest.mark.asyncio
async def test_scan_prunes_past_suggested_keeps_approved(db, owner, monkeypatch):
    # Seed a past suggested + a past approved directly.
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    db.add(EventSuggestion(tenant_id=owner, source="seatgeek", source_id="old-s",
                           title="Old Suggested", venue_name="Ball Arena",
                           starts_at=past, status="suggested"))
    db.add(EventSuggestion(tenant_id=owner, source="seatgeek", source_id="old-a",
                           title="Old Approved", venue_name="Ball Arena",
                           starts_at=past, status="approved"))
    await db.commit()
    monkeypatch.setattr(events_scan, "_fetch_seatgeek", _fake_sg([]))
    out = await events_scan.run_scan(db)
    assert out["pruned"] == 1
    remaining = {r.source_id for r in await _count(db, owner)}
    assert "old-a" in remaining and "old-s" not in remaining


def test_haversine_red_rocks_from_base():
    d = events_scan._haversine_mi(39.6005, -104.7926, 39.6654, -105.2057)
    assert 20 < d < 30


@pytest.mark.asyncio
async def test_scan_computes_distance(db, owner, monkeypatch):
    monkeypatch.setattr(events_scan, "_fetch_seatgeek", _fake_sg([
        _sg("20", "Ed Sheeran", "Empower Field at Mile High", 0.9, lat=39.7439, lng=-105.0201),
    ]))
    await events_scan.run_scan(db)
    row = (await db.execute(select(EventSuggestion).where(
        EventSuggestion.source_id == "20"))).scalar_one()
    assert row.distance_mi is not None and row.distance_mi > 0
