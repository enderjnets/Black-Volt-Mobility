"""Stage 2 — signed render-callback that delivers a real mp4 into /media.

Sets a render signing key so the HMAC-gated webhook can be exercised. Other test
modules send unsigned callbacks and still get 403 (no header → mismatch), so this
key is safe to set process-wide.
"""
import base64
import hashlib
import hmac
import json
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["SOCIAL_RENDER_SIGNING_KEY"] = "render-test-key"
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

import pytest_asyncio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402
from app.services import social as S  # noqa: E402
from app.services.tenancy import get_default_tenant  # noqa: E402

client = TestClient(app)
_KEY = b"render-test-key"
# Minimal bytes that pass the mp4 magic sniff (ftyp box at offset 4).
_FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 48


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


def _sig(body: bytes) -> str:
    return base64.b64encode(hmac.new(_KEY, body, hashlib.sha256).digest()).decode()


def _callback(payload: dict, sign: bool = True):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        headers["x-bv-render-signature"] = _sig(body)
    return client.post("/api/v1/social/webhooks/render", content=body, headers=headers)


async def _armed_post(db, tid: int) -> int:
    """A post in the `render_requested` state (what the live render path sets) —
    the only state a render callback may attach to."""
    post = await S.create_post(db, tenant_id=tid, content={"caption": "c"}, lang="en")
    row = await S._get_post(db, tenant_id=tid, post_id=post["id"])
    row.status = "render_requested"
    await db.commit()
    return post["id"]


async def test_signed_callback_writes_real_asset(db):
    tid = (await get_default_tenant(db)).id
    pid = await _armed_post(db, tid)
    r = _callback({
        "job_id": "job_x", "tenant_id": tid, "post_id": pid,
        "media_b64": base64.b64encode(_FAKE_MP4).decode(), "media_ext": "mp4",
    })
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "applied"
    rows = await S.list_posts(db, tenant_id=tid)
    got = next(p for p in rows if p["id"] == pid)
    assert got["status"] == "rendered"
    assert got["simulated_render"] is False
    assert got["media_path"].startswith(f"tenants/{tid}/social/video-")
    # The file physically landed under the public /media root.
    assert os.path.exists(os.path.join(get_settings().MEDIA_DIR, got["media_path"]))
    # A replayed callback for the now-rendered post is a no-op (idempotent).
    r2 = _callback({
        "job_id": "job_x", "tenant_id": tid, "post_id": pid,
        "media_b64": base64.b64encode(_FAKE_MP4).decode(), "media_ext": "mp4",
    })
    assert r2.json()["result"] == "ignored"


async def test_callback_rejects_non_video(db):
    tid = (await get_default_tenant(db)).id
    pid = await _armed_post(db, tid)
    r = _callback({
        "job_id": "job_y", "tenant_id": tid, "post_id": pid,
        "media_b64": base64.b64encode(b"this is not a video").decode(), "media_ext": "mp4",
    })
    assert r.status_code == 200
    assert r.json()["result"] == "rejected_asset"
    rows = await S.list_posts(db, tenant_id=tid)
    got = next(p for p in rows if p["id"] == pid)
    assert got["status"] == "failed"


async def test_callback_rejects_bad_extension(db):
    tid = (await get_default_tenant(db)).id
    pid = await _armed_post(db, tid)
    r = _callback({
        "job_id": "job_z", "tenant_id": tid, "post_id": pid,
        "media_b64": base64.b64encode(_FAKE_MP4).decode(), "media_ext": "exe",
    })
    assert r.json()["result"] == "rejected_asset"


def test_callback_bad_signature_is_403():
    r = _callback({"tenant_id": 1, "post_id": 1, "media_b64": "x"}, sign=False)
    assert r.status_code == 403


async def test_callback_unknown_post_ignored(db):
    r = _callback({"job_id": "j", "tenant_id": 999999, "post_id": 999999,
                   "media_b64": base64.b64encode(_FAKE_MP4).decode(), "media_ext": "mp4"})
    assert r.status_code == 200
    assert r.json()["result"] == "ignored"
