"""Image-vs-video social posts: an image post uses the owner's uploaded photo directly
(no video render), video posts are unchanged. Simulated; deterministic template path.
"""

import base64
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["SOCIAL_PUBLISH_VIA_BUFFER"] = "false"
os.environ["BUFFER_API_KEY"] = ""
os.environ["BUFFER_ORG_ID"] = ""
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Tenant  # noqa: E402
from app.services import render_client  # noqa: E402
from app.services import social as S  # noqa: E402

# 1x1 transparent PNG.
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
    t = Tenant(slug=f"img-{uuid.uuid4().hex[:8]}", name="Img Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


@pytest.mark.asyncio
async def test_image_post_uses_photo_and_skips_render(db):
    tid = await _mk_tenant(db)
    saved = S.save_reference_image(tid, raw=_PNG)
    assert saved is not None
    rel_path, _ = saved

    out = await S.generate_and_create(
        db, tenant_id=tid, topic="airport pickup", angle=None, lang="en",
        reference_paths=[rel_path], media_kind="image",
    )
    assert out["media_kind"] == "image"
    assert out["status"] == "rendered"  # ready for approval, no render step
    assert out["media_path"] == rel_path  # the photo IS the media
    assert out["cover_path"] == rel_path
    assert out["simulated_render"] is False  # a real image, not the sim-video sentinel
    assert out["media_path"] != render_client.SIMULATED_MEDIA


@pytest.mark.asyncio
async def test_request_render_is_noop_for_image_post(db):
    tid = await _mk_tenant(db)
    rel_path, _ = S.save_reference_image(tid, raw=_PNG)
    out = await S.generate_and_create(
        db, tenant_id=tid, topic="t", angle=None, lang="en",
        reference_paths=[rel_path], media_kind="image",
    )
    # Re-requesting a render on an image post just re-finalizes to the photo (no worker).
    again = await S.request_render(db, tenant_id=tid, post_id=out["id"])
    assert again["media_kind"] == "image"
    assert again["media_path"] == rel_path
    assert again["media_path"] != render_client.SIMULATED_MEDIA


@pytest.mark.asyncio
async def test_image_post_without_photo_stays_draft_for_ai_render(db):
    # Phase 2: an image post with no photo is NOT finalized — it stays a draft so the
    # caller can kick off the AI text→image render (the /generate API does that).
    tid = await _mk_tenant(db)
    out = await S.generate_and_create(
        db, tenant_id=tid, topic="t", angle=None, lang="en",
        reference_paths=None, media_kind="image",
    )
    assert "error" not in out
    assert out["media_kind"] == "image"
    assert out["status"] == "draft"
    assert out["media_path"] is None


@pytest.mark.asyncio
async def test_request_render_submits_ai_image_when_no_photo(db):
    # Phase 2: image post with no photo → request_render submits an AI text→image job
    # (rather than finalizing to an uploaded photo). Simulated render returns immediately.
    tid = await _mk_tenant(db)
    out = await S.generate_and_create(
        db, tenant_id=tid, topic="t", angle=None, lang="en", media_kind="image",
    )
    assert out["status"] == "draft"
    res = await S.request_render(db, tenant_id=tid, post_id=out["id"])
    assert res is not None
    assert res["media_kind"] == "image"
    assert res["status"] in ("rendered", "render_requested")


@pytest.mark.asyncio
async def test_video_post_is_unchanged(db):
    tid = await _mk_tenant(db)
    out = await S.generate_and_create(
        db, tenant_id=tid, topic="t", angle=None, lang="en", media_kind="video",
    )
    assert out["media_kind"] == "video"
    assert out["status"] == "draft"  # video still needs a separate render request
    assert out["media_path"] is None
