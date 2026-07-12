"""Volt Blog Autopilot — our own "Soro" AI SEO blog engine.

Creates four tenant-scoped tables:
  - blog_configs   (one per tenant: Brand DNA + autopilot knobs + embed token + GSC link)
  - blog_keywords  (discovered/planned keywords)
  - blog_posts     (bilingual generated articles with SSR landing pages)
  - seo_snapshots  (daily GSC + PageSpeed captures)

New tables only — no existing table is touched. Matches app/models/blog.py.

Revision ID: 0044_blog_engine
Revises: 0043_event_series_key
Create Date: 2026-07-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_blog_engine"
down_revision = "0043_event_series_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blog_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("voice", sa.Text(), nullable=True),
        sa.Column("audience", sa.Text(), nullable=True),
        sa.Column("key_themes", sa.JSON(), nullable=True),
        sa.Column("avoid_topics", sa.JSON(), nullable=True),
        sa.Column("image_style", sa.Text(), nullable=True),
        sa.Column("cadence_per_week", sa.Integer(), server_default="5", nullable=False),
        sa.Column("autopublish", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("paused", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("languages", sa.JSON(), nullable=True),
        sa.Column("embed_token", sa.String(length=64), nullable=False),
        sa.Column("gsc_site_url", sa.String(length=240), nullable=True),
        sa.Column("gsc_refresh_token", sa.Text(), nullable=True),
        sa.Column("gsc_connected_email", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", name="uq_blog_config_tenant"),
    )
    op.create_index("ix_blog_configs_tenant_id", "blog_configs", ["tenant_id"])
    op.create_index("ix_blog_configs_embed_token", "blog_configs", ["embed_token"], unique=True)

    op.create_table(
        "blog_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(length=200), nullable=False),
        sa.Column("lang", sa.String(length=5), server_default="en", nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("volume_est", sa.Integer(), nullable=True),
        sa.Column("difficulty_est", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="candidate", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "keyword", "lang", name="uq_blog_keyword"),
    )
    op.create_index("ix_blog_keywords_tenant_id", "blog_keywords", ["tenant_id"])
    op.create_index("ix_blog_keywords_status", "blog_keywords", ["status"])

    op.create_table(
        "blog_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "keyword_id",
            sa.Integer(),
            sa.ForeignKey("blog_keywords.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slug", sa.String(length=90), nullable=False),
        sa.Column("title_en", sa.String(length=200), nullable=False),
        sa.Column("title_es", sa.String(length=200), nullable=True),
        sa.Column("excerpt_en", sa.Text(), nullable=True),
        sa.Column("excerpt_es", sa.Text(), nullable=True),
        sa.Column("body_md_en", sa.Text(), nullable=True),
        sa.Column("body_md_es", sa.Text(), nullable=True),
        sa.Column("hero_path", sa.String(length=300), nullable=True),
        sa.Column("hero_alt", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="generating", nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("render_progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("render_stage", sa.String(length=40), nullable=True),
        sa.Column(
            "social_post_id",
            sa.Integer(),
            sa.ForeignKey("social_posts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_blog_post_slug"),
    )
    op.create_index("ix_blog_posts_tenant_id", "blog_posts", ["tenant_id"])
    op.create_index("ix_blog_posts_slug", "blog_posts", ["slug"], unique=True)
    op.create_index("ix_blog_posts_status", "blog_posts", ["status"])

    op.create_table(
        "seo_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "kind", "date", name="uq_seo_snapshot"),
    )
    op.create_index("ix_seo_snapshots_tenant_id", "seo_snapshots", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("seo_snapshots")
    op.drop_table("blog_posts")
    op.drop_table("blog_keywords")
    op.drop_table("blog_configs")
