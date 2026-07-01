"""Daily auto-post helpers: media-kind resolution, brand-photo library pick, seasonal
hint, and the smart brief (own analytics + season → topic/angle) fallback.
"""

import base64
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Tenant  # noqa: E402
from app.services import social as S  # noqa: E402

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
    t = Tenant(slug=f"day-{uuid.uuid4().hex[:8]}", name="Day Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


def test_daily_media_kind_resolution():
    assert S._daily_media_kind("video", 0) == "video"
    assert S._daily_media_kind("image", 5) == "image"
    assert S._daily_media_kind(None, 3) == "video"
    assert S._daily_media_kind("mixed", 2) == "image"  # even day
    assert S._daily_media_kind("mixed", 3) == "video"  # odd day


def test_season_hint_by_month():
    assert "ski" in S._season_hint(1).lower()
    assert "summer" in S._season_hint(7).lower()
    assert "fall" in S._season_hint(10).lower()


def test_pick_brand_photo_empty_returns_none():
    # A tenant id that has never uploaded → no refs dir.
    assert S._pick_brand_photo(99_000_001) is None


@pytest.mark.asyncio
async def test_pick_brand_photo_returns_a_saved_photo(db):
    tid = await _mk_tenant(db)
    rel_path, _ = S.save_reference_image(tid, raw=_PNG)
    picked = S._pick_brand_photo(tid)
    assert picked is not None
    assert picked.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
    assert f"/{tid}/" in picked.replace("\\", "/")  # scoped to this tenant


@pytest.mark.asyncio
async def test_smart_daily_brief_falls_back_without_analytics(db):
    tid = await _mk_tenant(db)
    topic, angle = await S._smart_daily_brief(db, tenant_id=tid, seed=42)
    # No conversion data yet → no route topic, but a seasonal angle is always returned.
    assert topic is None
    assert "Seasonal focus" in angle
    assert angle.strip() != ""
