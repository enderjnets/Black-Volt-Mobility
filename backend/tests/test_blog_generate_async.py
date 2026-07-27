"""Starting an article must not depend on the article finishing.

Two long model calls take longer than the 100 second ceiling every reverse proxy in front
of this app enforces, so the old synchronous endpoint returned a 500 to the owner while the
article was written anyway — he pressed the button, saw it fail, and stopped trusting it.
The request now only starts the job.

Isolated blackvolt_test DB only.
"""
import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["KIMI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1 import blog as blog_api  # noqa: E402
from app.main import app  # noqa: E402
from app.services.tenancy import owner_tenant_id  # noqa: E402


def _owner_tenant() -> int:
    """Resolved the same way the endpoint resolves it, on its own short-lived engine."""
    async def go():
        engine = create_async_engine(get_settings().DATABASE_URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                return await owner_tenant_id(db)
        finally:
            await engine.dispose()

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _clear_inflight():
    blog_api._writing.clear()
    yield
    blog_api._writing.clear()
    blog_api._write_tasks.clear()


def _client() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def test_generate_returns_immediately_with_202():
    c = _client()
    r = c.post("/api/v1/blog/admin/generate", json={"keyword": "Boulder to DEN airport"})
    assert r.status_code == 202
    assert r.json() == {"status": "generating"}


def test_a_click_while_a_job_is_in_flight_is_refused():
    """Double-tapping the button would otherwise mean two articles for one keyword.

    The in-flight set is seeded directly: TestClient tears down the background task with the
    request, so a second real request would always find the lock already released.
    """
    blog_api._writing.add(_owner_tenant())
    c = _client()
    r = c.post("/api/v1/blog/admin/generate", json={"keyword": "Denver to Vail transfer"})
    assert r.status_code == 409
    assert r.json()["detail"] == "already_writing"


def test_write_next_with_an_empty_queue_fails_fast():
    """Better a 400 now than two minutes of silence and nothing to show for it."""
    c = _client()
    r = c.post("/api/v1/blog/admin/generate", json={})
    assert r.status_code == 400
    assert r.json()["detail"] == "need_keyword"


def test_a_crashing_job_releases_the_lock_and_swallows_the_error(monkeypatch):
    """If generation blows up, the owner must still be able to press the button again —
    and the exception must not escape into an unhandled task."""
    async def boom(*a, **kw):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(blog_api.blog_writer, "generate_article", boom)
    tid = _owner_tenant()
    blog_api._writing.add(tid)
    asyncio.run(blog_api._generate_in_background(tid, None, "Aspen private transfer"))
    assert tid not in blog_api._writing


def test_a_finished_job_releases_the_lock():
    tid = _owner_tenant()
    blog_api._writing.add(tid)
    asyncio.run(blog_api._generate_in_background(tid, None, "Aspen private transfer"))
    assert tid not in blog_api._writing
