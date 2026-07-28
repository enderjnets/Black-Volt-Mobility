"""Volt Blog Autopilot — publisher.

Releases `scheduled` articles once their 24h edit window elapses (hybrid autopilot),
gated by the tenant's `autopublish` flag. On publish it (F4) fires an auto-share to
social and pings the sitemap. Runs on a short interval from the scheduler.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlogPost
from app.services import blog as blog_service

logger = logging.getLogger("blackvolt.blog.publish")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def _auto_share(db: AsyncSession, *, tenant_id: int, post: BlogPost) -> None:
    """Create an auto-share social post for a freshly published article. Wired in F4;
    best-effort and never blocks publishing."""
    try:
        from app.services import blog_share

        await blog_share.share_post(db, tenant_id=tenant_id, post=post)
    except Exception as e:  # noqa: BLE001 — auto-share must never block publish
        logger.info("blog auto-share skipped post=%s: %s", post.id, e)


async def publish_now(db: AsyncSession, *, tenant_id: int, post_id: int) -> dict | None:
    """Publish one article because the owner said so. Right now, not eventually.

    This used to live in blog_service and only moved `publish_at` forward, leaving the
    status `scheduled` for the background job to pick up — a job that returns early while
    the blog is paused. So "Publish now" answered 200 OK and did nothing, for ever. An
    explicit owner action is not the autopilot and is not gated by it: `paused` means stop
    the robot, not stop the person.

    A `draft` is publishable here on purpose: holding an article back is only useful if
    overriding the hold is one click.
    """
    post = await blog_service.get_post(db, tenant_id=tenant_id, post_id=post_id)
    if post is None or post.status not in ("scheduled", "generating", "draft"):
        return None
    now = _now()
    post.status = "published"
    post.published_at = now
    post.publish_at = post.publish_at or now
    await db.commit()
    await db.refresh(post)
    await _auto_share(db, tenant_id=tenant_id, post=post)
    logger.info("blog published by owner tenant=%s post=%s slug=%s", tenant_id, post.id, post.slug)
    return blog_service._admin_post_dict(post)


async def publish_due(db: AsyncSession, *, tenant_id: int) -> dict:
    """Publish every scheduled post whose 24h window has elapsed (autopublish only)."""
    cfg = await blog_service.ensure_config(db, tenant_id=tenant_id)
    if cfg.paused or not cfg.autopublish:
        return {"skipped": "paused_or_manual"}

    now = _now()
    due = (
        await db.execute(
            select(BlogPost).where(
                BlogPost.tenant_id == tenant_id,
                BlogPost.status == "scheduled",
                BlogPost.publish_at.is_not(None),
                BlogPost.publish_at <= now,
            )
        )
    ).scalars().all()

    published = 0
    for post in due:
        post.status = "published"
        post.published_at = now
        published += 1
    if published:
        await db.commit()
        for post in due:
            await db.refresh(post)
            await _auto_share(db, tenant_id=tenant_id, post=post)
    logger.info("blog publish_due tenant=%s published=%s", tenant_id, published)
    return {"published": published}
