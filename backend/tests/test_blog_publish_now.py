"""Pressing "Publish now" has to publish.

The owner pressed it twice on a finished article and got 200 OK both times; the post stayed
`scheduled` and never went live. `publish_now` only moved `publish_at` forward and left the
real work to the background job — which returns early while the blog is paused. It had no
test, which is how it survived.

An explicit owner action is not the autopilot: `paused` stops the robot, not the person.

Isolated blackvolt_test DB only.
"""
import datetime as dt
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

from app.models import BlogPost, Tenant  # noqa: E402
from app.services import blog as blog_service  # noqa: E402
from app.services import blog_publish  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


def _now():
    return dt.datetime.now(dt.UTC)


async def _tenant(db) -> int:
    t = Tenant(slug=f"pubnow-{uuid.uuid4().hex[:8]}", name="Publish Now Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.id


async def _post(db, tid: int, *, status: str, publish_at=None) -> BlogPost:
    p = BlogPost(
        tenant_id=tid, slug=f"pn-{uuid.uuid4().hex[:8]}", title_en="T",
        body_md_en="body", status=status, publish_at=publish_at,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def test_publishing_a_scheduled_post_actually_publishes_it(db):
    """THE bug: this used to return 200 with the post still sitting at `scheduled`."""
    tid = await _tenant(db)
    post = await _post(db, tid, status="scheduled", publish_at=_now() + dt.timedelta(hours=20))
    out = await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id)
    assert out is not None
    assert out["status"] == "published"
    assert out["published_at"] is not None
    row = await blog_service.get_post(db, tenant_id=tid, post_id=post.id)
    assert row.status == "published"
    assert row.published_at is not None


async def test_it_publishes_even_while_the_autopilot_is_paused(db):
    """Paused stops the robot. The owner pressing a button is not the robot."""
    tid = await _tenant(db)
    await blog_service.update_config(db, tenant_id=tid, patch={"paused": True})
    post = await _post(db, tid, status="scheduled", publish_at=_now() + dt.timedelta(hours=20))
    out = await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id)
    assert out["status"] == "published"
    # And the background job still refuses to act on its own while paused.
    assert (await blog_publish.publish_due(db, tenant_id=tid)).get("skipped")


async def test_it_publishes_even_when_autopublish_is_off(db):
    """Manual mode means the owner publishes by hand — that has to work."""
    tid = await _tenant(db)
    await blog_service.update_config(db, tenant_id=tid, patch={"autopublish": False})
    post = await _post(db, tid, status="scheduled", publish_at=_now() + dt.timedelta(hours=20))
    assert (await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id))["status"] == (
        "published"
    )


async def test_a_draft_can_be_published_over_the_gate(db):
    """Holding an article back is only useful if overriding the hold is one click."""
    tid = await _tenant(db)
    post = await _post(db, tid, status="draft")
    out = await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id)
    assert out is not None
    assert out["status"] == "published"
    row = await blog_service.get_post(db, tenant_id=tid, post_id=post.id)
    assert row.publish_at is not None  # never left null, or reads as "unscheduled" forever


async def test_an_already_published_post_is_refused(db):
    """No silent re-publish that would rewrite published_at and re-share it."""
    tid = await _tenant(db)
    post = await _post(db, tid, status="published")
    assert await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id) is None


async def test_an_archived_post_is_refused(db):
    tid = await _tenant(db)
    post = await _post(db, tid, status="archived")
    assert await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id) is None


async def test_another_tenants_post_is_invisible(db):
    tid, other = await _tenant(db), await _tenant(db)
    post = await _post(db, other, status="scheduled")
    assert await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id) is None


async def test_a_published_post_shows_up_in_the_public_feed(db):
    """The end-to-end point of the button: the reader can now see it."""
    tid = await _tenant(db)
    post = await _post(db, tid, status="scheduled", publish_at=_now() + dt.timedelta(hours=20))
    await blog_publish.publish_now(db, tenant_id=tid, post_id=post.id)
    slugs = [
        p["slug"] for p in await blog_service.list_public_posts(db, tenant_id=tid, lang="en")
    ]
    assert post.slug in slugs
