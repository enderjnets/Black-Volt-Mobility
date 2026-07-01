"""Image-vs-video social posts: an image post uses the owner's uploaded photo directly
(no video render), video posts are unchanged. Simulated; deterministic template path.
"""

import base64
import io
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


async def _mk_render_requested_image(db, tid: int) -> int:
    out = await S.generate_and_create(
        db, tenant_id=tid, topic="t", angle=None, lang="en", media_kind="image",
    )
    row = await S._get_post(db, tenant_id=tid, post_id=out["id"])
    row.status = "render_requested"
    await db.commit()
    return out["id"]


@pytest.mark.asyncio
async def test_render_callback_writes_image_asset(db):
    # Regression: the AI text→image render delivers a jpg/png; the callback must
    # persist it (was rejected as "not a video" → post stuck FAILED).
    tid = await _mk_tenant(db)
    pid = await _mk_render_requested_image(db, tid)
    result = await S.apply_render_callback(
        db,
        payload={
            "post_id": pid,
            "tenant_id": tid,
            "media_b64": base64.b64encode(_PNG).decode(),
            "media_ext": "png",
        },
    )
    assert result == "applied"
    row = await S._get_post(db, tenant_id=tid, post_id=pid)
    assert row.status == "rendered"
    assert row.media_path and row.media_path.endswith(".png")
    assert "/image-" in "/" + row.media_path  # server-named image-<ts>.png
    assert row.cover_path == row.media_path  # the image is its own cover


@pytest.mark.asyncio
async def test_render_callback_rejects_junk_as_image(db):
    tid = await _mk_tenant(db)
    pid = await _mk_render_requested_image(db, tid)
    result = await S.apply_render_callback(
        db,
        payload={
            "post_id": pid,
            "tenant_id": tid,
            "media_b64": base64.b64encode(b"not a real png").decode(),
            "media_ext": "png",
        },
    )
    assert result == "rejected_asset"
    row = await S._get_post(db, tenant_id=tid, post_id=pid)
    assert row.status == "failed"
    assert not row.media_path


def test_downscale_oversized_image_for_tiktok():
    # Uploaded photos bigger than TikTok's 1920x1080 photo limit must be shrunk to
    # publish (post 63 was 2252x3290 → TikTok "Invalid post").
    from PIL import Image as _Img

    buf = io.BytesIO()
    _Img.new("RGB", (2252, 3290), (10, 20, 30)).save(buf, format="JPEG")
    out = S._downscale_for_social(buf.getvalue(), "jpg")
    assert out is not None
    data, ext, ctype = out
    assert ext == "jpg" and ctype == "image/jpeg"
    w, h = _Img.open(io.BytesIO(data)).size
    assert max(w, h) <= 1920 and min(w, h) <= 1080
    assert abs((w / h) - (2252 / 3290)) < 0.01  # aspect preserved


def test_downscale_keeps_small_image_untouched():
    from PIL import Image as _Img

    buf = io.BytesIO()
    _Img.new("RGB", (768, 1344), (0, 0, 0)).save(buf, format="PNG")
    # Within limits → None means "use the original bytes unchanged".
    assert S._downscale_for_social(buf.getvalue(), "png") is None
