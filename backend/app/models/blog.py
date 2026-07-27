"""Volt Blog Autopilot — our own "Soro": AI SEO blog engine.

Daily loop: keyword discovery → content calendar → bilingual (EN+ES) AI article with a
hero image → SSR blog page → auto-share to social → Search Console / PageSpeed analytics.

Four tables, all tenant-scoped (single public brand today, multi-tenant-ready for an
embeddable SaaS later):
  - BlogConfig   — one row per tenant: Brand DNA + autopilot settings + embed token + GSC link.
  - BlogKeyword  — discovered/planned keywords with volume/difficulty/score.
  - BlogPost     — the generated articles (bilingual body, hero, hybrid-24h publish window).
  - SeoSnapshot  — daily GSC (Search Console) and PSI (PageSpeed) captures for the analytics tab.

String enums (no pg enum) so states can evolve without a migration — same convention as SocialPost.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Keyword lifecycle: surfaced → chosen for the calendar → turned into an article → owner-vetoed.
BLOG_KEYWORD_STATUSES = ("candidate", "planned", "written", "vetoed")
# Article lifecycle. `scheduled` = written and waiting out its 24h edit window (hybrid autopilot);
# `published` goes live and triggers auto-share; `failed` = generation error (retryable).
# `draft` = written but it did not pass the quality gate, so it will never publish itself —
# the owner reads `meta.quality_issues`, fixes it, and schedules it by hand (or bins it).
BLOG_POST_STATUSES = ("generating", "draft", "scheduled", "published", "archived", "failed")
# Snapshot kinds for the analytics tab.
SEO_SNAPSHOT_KINDS = ("gsc_day", "psi")


class BlogConfig(Base):
    """One row per tenant — the Brand DNA + autopilot knobs the writer is grounded on."""

    __tablename__ = "blog_configs"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_blog_config_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )

    # --- Brand DNA (grounds every article; owner-editable in the dashboard) ---
    voice: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_themes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    avoid_topics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    image_style: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Autopilot ---
    cadence_per_week: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    autopublish: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Which languages each article is generated in. Default = the whole site: EN + ES.
    languages: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- Embed (for external sites / future SaaS; our own site uses SSR, not this) ---
    embed_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # --- Google Search Console link (per-tenant OAuth; F4). Columns live here now so
    # connecting GSC later needs no migration. Tokens are user data, DB-only, never committed. ---
    gsc_site_url: Mapped[str | None] = mapped_column(String(240), nullable=True)
    gsc_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    gsc_connected_email: Mapped[str | None] = mapped_column(String(240), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BlogKeyword(Base):
    """A discovered keyword the calendar can turn into an article."""

    __tablename__ = "blog_keywords"
    __table_args__ = (
        UniqueConstraint("tenant_id", "keyword", "lang", name="uq_blog_keyword"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    keyword: Mapped[str] = mapped_column(String(200))
    lang: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    source: Mapped[str] = mapped_column(String(20))  # gsc | autocomplete | llm | events | manual
    volume_est: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty_est: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="candidate", server_default="candidate", index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BlogPost(Base):
    """A generated, bilingual SEO article with an SSR landing page at /blog/<slug>."""

    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    keyword_id: Mapped[int | None] = mapped_column(
        ForeignKey("blog_keywords.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(90), unique=True, index=True)

    # Bilingual content. `_es` may be empty when a tenant runs EN-only.
    title_en: Mapped[str] = mapped_column(String(200))
    title_es: Mapped[str | None] = mapped_column(String(200), nullable=True)
    excerpt_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpt_es: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_md_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_md_es: Mapped[str | None] = mapped_column(Text, nullable=True)

    hero_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    hero_alt: Mapped[str | None] = mapped_column(String(300), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default="generating", server_default="generating", index=True
    )
    # Hybrid autopilot: written articles wait until publish_at (now+24h) before going live,
    # giving the owner a window to edit or veto. autopublish=false keeps them here indefinitely.
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # internal_links (validated), faq [{q,a}], grounding refs used, keyword text — JSON blob.
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Hero render progress (mirrors SocialPost) when the image is produced by the render worker.
    render_progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    render_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # The auto-share SocialPost created when this article is published (nullable until then).
    social_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_posts.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SeoSnapshot(Base):
    """A daily SEO capture — Google Search Console day rollup or a PageSpeed audit."""

    __tablename__ = "seo_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "date", name="uq_seo_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # gsc_day | psi
    date: Mapped[str] = mapped_column(String(10))   # YYYY-MM-DD (Denver)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
