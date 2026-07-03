"""Event pricing: model columns, update_event allowlist, fee lines + round-trip suggestion."""

import datetime as dt
import os
import uuid
from zoneinfo import ZoneInfo

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["SOCIAL_PUBLISH_VIA_BUFFER"] = "false"
os.environ["SEATGEEK_CLIENT_ID"] = ""
os.environ["TICKETMASTER_API_KEY"] = ""
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""
os.environ["MAPS_SIMULATED"] = "true"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Event, Tenant  # noqa: E402
from app.services import event_pricing, events  # noqa: E402

_DENVER = ZoneInfo("America/Denver")


def _denver(y, mo, d, h, mi=0) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, tzinfo=_DENVER).astimezone(dt.UTC)


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
    """A tenant registered as the events owner (event lookups resolve to it)."""
    tid = await _mk_tenant(db)
    monkeypatch.setattr(get_settings(), "OWNER_TENANT_ID", tid)
    return tid


async def _mk_event(db, tid, **over) -> Event:
    defaults = dict(
        tenant_id=tid,
        slug=f"evt-{uuid.uuid4().hex[:8]}",
        title="Ed Sheeran",
        venue_key="empower_field",
        venue_name="Empower Field at Mile High",
        venue_address="1701 Bryant St, Denver, CO 80204",
        starts_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=2),
        status="published",
    )
    defaults.update(over)
    ev = Event(**defaults)
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@pytest.mark.asyncio
async def test_pricing_columns_defaults(db):
    tid = await _mk_tenant(db)
    ev = await _mk_event(db, tid)
    assert ev.event_fee == 0
    assert ev.night_fee == 25
    assert ev.night_cutoff == "21:00"
    assert ev.wait_fee_per_hour == 30
    assert ev.est_duration_hours == 3
    assert ev.round_trip_price is None
    assert ev.pricing_research is None


@pytest.mark.asyncio
async def test_update_event_accepts_pricing_fields(db):
    tid = await _mk_tenant(db)
    ev = await _mk_event(db, tid)
    out = await events.update_event(
        db,
        tenant_id=tid,
        event_id=ev.id,
        patch={
            "event_fee": 40,
            "night_fee": 30,
            "night_cutoff": "22:00",
            "wait_fee_per_hour": 35,
            "est_duration_hours": 3.5,
            "round_trip_price": 420,
        },
    )
    assert out["event_fee"] == 40
    assert out["night_fee"] == 30
    assert out["night_cutoff"] == "22:00"
    assert out["wait_fee_per_hour"] == 35
    assert out["est_duration_hours"] == 3.5
    assert out["round_trip_price"] == 420


@pytest.mark.asyncio
async def test_update_event_rejects_bad_pricing(db):
    tid = await _mk_tenant(db)
    ev = await _mk_event(db, tid, event_fee=10)
    out = await events.update_event(
        db,
        tenant_id=tid,
        event_id=ev.id,
        patch={
            "event_fee": -5,            # negative → rejected, keeps 10
            "night_cutoff": "9pm",      # bad format → rejected, keeps 21:00
            "wait_fee_per_hour": "abc",  # non-numeric → rejected, keeps 30
            "bogus": "x",               # unknown key → ignored
        },
    )
    assert out["event_fee"] == 10
    assert out["night_cutoff"] == "21:00"
    assert out["wait_fee_per_hour"] == 30
    assert "bogus" not in out


# --- Fee lines + night cutoff (America/Denver) ---


def _fake_event(**over) -> Event:
    base = dict(
        slug="ed-sheeran", title="Ed Sheeran", venue_key="empower_field",
        venue_name="Empower Field at Mile High",
        venue_address="1701 Bryant St, Denver, CO 80204",
        starts_at=_denver(2026, 7, 4, 20, 0), status="published",
        event_fee=40.0, night_fee=25.0, night_cutoff="21:00",
        wait_fee_per_hour=30.0, est_duration_hours=3.0, round_trip_price=None,
    )
    base.update(over)
    return Event(**base)


def test_event_fee_lines_night_applies():
    ev = _fake_event()
    lines = event_pricing.event_fee_lines(ev, leg_dt_utc=_denver(2026, 7, 4, 22, 0))
    labels = {x["label"]: x["amount"] for x in lines}
    assert labels == {"event_fee": 40.0, "night_fee": 25.0}


def test_event_fee_lines_daytime_no_night():
    ev = _fake_event()
    lines = event_pricing.event_fee_lines(ev, leg_dt_utc=_denver(2026, 7, 4, 18, 0))
    labels = {x["label"] for x in lines}
    assert labels == {"event_fee"}


def test_night_cutoff_boundary():
    # 20:59 Denver → before cutoff; 21:00 → at cutoff (inclusive).
    assert event_pricing._after_cutoff(_denver(2026, 7, 4, 20, 59), "21:00") is False
    assert event_pricing._after_cutoff(_denver(2026, 7, 4, 21, 0), "21:00") is True


def test_venue_matches_watchlist_and_generic():
    ev = _fake_event()
    assert event_pricing._venue_matches(ev, "Empower Field at Mile High, Denver, CO") is True
    assert event_pricing._venue_matches(ev, "123 Main St, Aurora, CO") is False
    gen = _fake_event(venue_key="generic", venue_name="Mission Ballroom",
                      venue_address="4242 Wynkoop St, Denver, CO")
    assert event_pricing._venue_matches(gen, "Mission Ballroom, Denver") is True
    assert event_pricing._venue_matches(gen, "4242 Wynkoop St, Denver, CO") is True
    # Whole-word match: a generic "Ballroom" event must NOT attach to "Ballwin".
    assert event_pricing._venue_matches(gen, "12 Ballwin Ave, Denver, CO") is False


def test_venue_match_by_street_address():
    # The event landing books to the venue's STREET address, not its name — a watchlist
    # venue must still match so its fees apply. (Regression: over-tight alias-only match.)
    ev = _fake_event()  # empower_field, address "1701 Bryant St, Denver, CO 80204"
    assert event_pricing._venue_matches(ev, "1701 Bryant St, Denver, CO 80204") is True
    assert event_pricing._venue_matches(ev, "1701 Bryant St., Denver, CO") is True
    assert event_pricing._venue_matches(ev, "999 Other St, Denver, CO") is False


def test_venue_match_no_substring_false_positive():
    # "Fiddler's Green" must not surcharge an unrelated ride to Greenwood Village.
    fiddlers = _fake_event(venue_key="fiddlers_green", venue_name="Fiddler's Green Amphitheatre",
                           venue_address="6350 Greenwood Plaza Blvd, Greenwood Village, CO")
    assert event_pricing._venue_matches(fiddlers, "6300 Greenwood Village, CO") is False
    assert event_pricing._venue_matches(fiddlers, "Fiddler's Green Amphitheatre, CO") is True


@pytest.mark.asyncio
async def test_find_event_for_ride_matches_and_misses(db, owner):
    ev = await _mk_event(db, owner, starts_at=_denver(2026, 7, 4, 20, 0))
    when = _denver(2026, 7, 4, 19, 0)
    found = await event_pricing.find_event_for_ride(
        db, pickup="Downtown Denver, CO", dropoff="Empower Field at Mile High, Denver, CO",
        when=when,
    )
    assert found is not None and found.id == ev.id
    # Wrong day → no match.
    assert await event_pricing.find_event_for_ride(
        db, pickup="Downtown Denver, CO", dropoff="Empower Field at Mile High, Denver, CO",
        when=_denver(2026, 7, 20, 19, 0),
    ) is None
    # Right time, unrelated venue → no match.
    assert await event_pricing.find_event_for_ride(
        db, pickup="Downtown Denver, CO", dropoff="Cherry Creek Mall, Denver, CO",
        when=when,
    ) is None


@pytest.mark.asyncio
async def test_build_quote_appends_event_fees(db, owner):
    from app.services import booking
    await _mk_event(db, owner, starts_at=_denver(2026, 7, 4, 20, 0), event_fee=40, night_fee=25)
    q = await booking.build_quote(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 22, 0),
    )
    labels = {x["label"] for x in q["lines"]}
    assert "event_fee" in labels and "night_fee" in labels
    assert q["event"]["slug"]
    # apply_event_fees=False leaves the base fare untouched.
    q2 = await booking.build_quote(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 22, 0), apply_event_fees=False,
    )
    assert "event_fee" not in {x["label"] for x in q2["lines"]}


@pytest.mark.asyncio
async def test_suggest_round_trip_math_override_cap(db, owner):
    ev = await _mk_event(
        db, owner, starts_at=_denver(2026, 7, 4, 20, 0),
        event_fee=40, night_fee=25, wait_fee_per_hour=30, est_duration_hours=3,
    )
    out = await event_pricing.suggest_round_trip(db, event=ev, origin="Downtown Denver, CO")
    labels = {x["label"] for x in out["lines"]}
    assert {"ride_out", "ride_return", "event_fee", "night_fee", "wait_fee"} <= labels
    # ride legs are the denver_metro flat ($120 each) → 240 + 40 + 25 + 90 = 395.
    assert out["formula_total"] == 395.0
    assert out["total"] == 395.0 and out["overridden"] is False and out["capped"] is False

    # Uber cap: below-formula estimate trims the suggestion to 0.92×uber.
    capped = await event_pricing.suggest_round_trip(
        db, event=ev, origin="Downtown Denver, CO", uber_black=300,
    )
    assert capped["capped"] is True
    assert capped["total"] == round(0.92 * 300, 2)

    # Admin override wins over everything.
    ev.round_trip_price = 500
    await db.commit()
    ovr = await event_pricing.suggest_round_trip(
        db, event=ev, origin="Downtown Denver, CO", uber_black=300,
    )
    assert ovr["overridden"] is True and ovr["total"] == 500.0


@pytest.mark.asyncio
async def test_public_event_exposes_prices_not_strategy(db, owner):
    ev = await _mk_event(
        db, owner, starts_at=_denver(2026, 7, 4, 20, 0),
        event_fee=40, night_fee=25, wait_fee_per_hour=30, est_duration_hours=3,
    )
    ev.status = "published"
    await db.commit()
    pub = await events.get_public_event(db, slug=ev.slug)
    assert pub is not None
    assert pub["one_way_from"] == 160.0  # 120 flat + 40 event fee
    assert pub["round_trip_price"] == 395.0  # 240 + 40 + 25 + 90
    assert "return_at" in pub
    # Internal strategy / raw fees must not leak publicly.
    for leaked in ("pricing_research", "night_fee", "wait_fee_per_hour", "est_duration_hours"):
        assert leaked not in pub

    # Admin override is reflected publicly.
    ev.round_trip_price = 350
    await db.commit()
    pub2 = await events.get_public_event(db, slug=ev.slug)
    assert pub2["round_trip_price"] == 350.0
