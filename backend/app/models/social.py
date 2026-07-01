"""Social-media module models (Phase "Social").

Three tenant-scoped tables back the owner-approval social workflow:

- `SocialAccount`  — a connected platform (Instagram/Facebook/TikTok) + its OAuth
  tokens. Tokens are written/read server-side only and never committed
  (CLAUDE.md anti-pattern #2).
- `SocialPost`     — one piece of content moving through the pipeline
  (draft → render_requested → rendered → approved → scheduled → published).
  Every post waits for the owner's approval before it can publish.
- `SocialInteraction` — a comment / DM pulled from a platform, with the AI-drafted
  reply the owner approves before it sends. `text` is UNTRUSTED (it comes from the
  public) and is never fed to the LLM as instructions.

Enum-like fields use validated String columns (mirroring `PlatformStat.platform`)
rather than Postgres enums, so the small state sets can evolve across stages
without an enum migration. Allowed values are documented inline and enforced in
the service layer.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Allowed platforms (fixed set — only these ever reach an LLM prompt or API call).
SOCIAL_PLATFORMS = ("instagram", "facebook", "tiktok")
# Post lifecycle.
POST_STATUSES = (
    "draft",
    "render_requested",
    "rendered",
    "approved",
    "scheduled",
    "published",
    "failed",
)
# Comment/DM reply lifecycle.
REPLY_STATUSES = ("pending", "drafted", "approved", "sent", "dismissed")
# Account connection states.
ACCOUNT_STATUSES = ("connected", "expired", "disconnected")


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    # One row per platform per tenant.
    __table_args__ = (
        UniqueConstraint("tenant_id", "platform", name="uq_social_account_tenant_platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(20))  # SOCIAL_PLATFORMS

    external_account_id: Mapped[str | None] = mapped_column(String(190), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(190), nullable=True)
    # OAuth tokens — server-side only, never logged, never committed.
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="disconnected")  # ACCOUNT_STATUSES

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SocialPost(Base):
    __tablename__ = "social_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )

    # Content (all AI-assisted, owner-editable).
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # "video" (default — Kling render on the ROG worker) or "image" (the owner's uploaded
    # photo used directly, no render). Governs the render + publish path.
    media_kind: Mapped[str] = mapped_column(String(8), nullable=False, server_default="video")
    # Rendered asset, relative to the public /media mount.
    media_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Target platforms — a subset of SOCIAL_PLATFORMS. Defaulted in the service.
    targets: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    # Owner-uploaded reference images (vehicles, backgrounds…) the worker animates
    # into the video. Stored as rel paths under the public /media mount; always
    # scoped to this tenant's social/refs dir (validated on write).
    reference_image_paths: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list
    )

    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)  # POST_STATUSES
    render_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Live render progress (0–100) + current stage key, reported by the worker via
    # the signed /social/webhooks/render/progress webhook while status is
    # "render_requested". Null until a render is requested; the frontend draws a
    # progress bar from these and clears it once the final asset arrives.
    render_progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    render_stage: Mapped[str | None] = mapped_column(String(48), nullable=True)
    # Last reason the owner gave when rejecting this post. Stored for display and
    # used to regenerate a corrected draft; also logged to SocialFeedback so the
    # brand "learns" across all future posts.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # {platform: external_post_id} once published. Defaulted in the service.
    external_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    lang: Mapped[str] = mapped_column(String(2), default="en")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SocialFeedback(Base):
    """A "lesson" the owner taught the AI by rejecting a post with a reason. These
    accumulate per tenant and are injected (most-recent-distinct) into every future
    brief's system prompt so the AI stops repeating the same mistakes. Tenant-scoped;
    one tenant never learns from another's feedback."""

    __tablename__ = "social_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # The post whose rejection produced this lesson (nullable; not an FK so deleting
    # the post never erases the lesson the brand learned from it).
    post_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SocialInteraction(Base):
    __tablename__ = "social_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # The post the comment is on (nullable: a DM may not map to one of our posts).
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_posts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(20))  # SOCIAL_PLATFORMS
    external_post_id: Mapped[str | None] = mapped_column(String(190), nullable=True)
    external_comment_id: Mapped[str | None] = mapped_column(
        String(190), nullable=True, index=True
    )
    author_handle: Mapped[str | None] = mapped_column(String(190), nullable=True)
    # UNTRUSTED public text — never sent to the LLM as instructions, only as data.
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(2), default="en")
    ai_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # REPLY_STATUSES
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
