"""EventSuggestion + Event models: persistence roundtrip and defaults."""

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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Event, EventSuggestion, Tenant  # noqa: E402


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


@pytest.mark.asyncio
async def test_models_roundtrip(db):
    tid = await _mk_tenant(db)
    s = EventSuggestion(
        tenant_id=tid,
        source="seatgeek",
        source_id=f"sg-{uuid.uuid4().hex[:8]}",
        title="Ed Sheeran",
        performer="Ed Sheeran",
        venue_name="Empower Field at Mile High",
        venue_key="empower_field",
        starts_at=dt.datetime(2026, 8, 14, 19, 0, tzinfo=dt.timezone.utc),
        score=0.9,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    assert s.status == "suggested"
    assert s.created_at is not None

    e = Event(
        tenant_id=tid,
        suggestion_id=s.id,
        slug=f"ed-sheeran-empower-field-2026-{uuid.uuid4().hex[:6]}",
        title="Ed Sheeran",
        venue_name=s.venue_name,
        starts_at=s.starts_at,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    assert e.status == "draft"
    assert e.venue_key == "generic"  # server_default


@pytest.mark.asyncio
async def test_unique_source_constraint(db):
    tid = await _mk_tenant(db)
    sid = f"dup-{uuid.uuid4().hex[:8]}"
    common = dict(
        tenant_id=tid, source="seatgeek", source_id=sid, title="X",
        venue_name="V", starts_at=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
    )
    db.add(EventSuggestion(**common))
    await db.commit()
    db.add(EventSuggestion(**common))
    with pytest.raises(Exception):  # unique (source, source_id)
        await db.commit()
    await db.rollback()
