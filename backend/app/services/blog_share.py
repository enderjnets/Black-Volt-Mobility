"""Volt Blog Autopilot — social auto-share.

When an article is published, drop a ready-to-review social post into the existing
social pipeline (draft → owner approves → Buffer). We create a DRAFT (never auto-post
to Buffer without approval — same observer-first stance as the rest of social), linked
to the article via BlogPost.social_post_id, carrying the hero image + a link back to the
SSR article.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import BlogPost
from app.services import social

logger = logging.getLogger("blackvolt.blog.share")


def _caption(post: BlogPost, url: str) -> str:
    excerpt = (post.excerpt_en or "").strip()
    lead = excerpt or post.title_en
    return f"{lead}\n\nRead the full guide → {url}"


async def share_post(db: AsyncSession, *, tenant_id: int, post: BlogPost) -> dict | None:
    """Create (once) a draft social post for a freshly published article."""
    if post.social_post_id:
        return None  # already shared
    site = get_settings().PUBLIC_SITE_URL.rstrip("/")
    url = f"{site}/blog/{post.slug}"
    content = {
        "topic": post.title_en,
        "caption": _caption(post, url),
        "hashtags": "#Denver #DenverEV #RedRocks #DIA #LuxuryTravel #BlackVoltMobility",
    }
    out = await social.create_post(
        db, tenant_id=tenant_id, content=content, lang="en",
        reference_paths=[post.hero_path] if post.hero_path else None,
        media_kind="image",
    )
    post.social_post_id = out.get("id")
    await db.commit()
    logger.info("blog auto-share draft created post=%s social=%s", post.id, post.social_post_id)
    return out
