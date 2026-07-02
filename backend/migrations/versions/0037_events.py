"""event_suggestions + events tables for the featured-events module

Revision ID: 0037_events
Revises: 0036_social_media_kind
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_events"
down_revision = "0036_social_media_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("performer", sa.String(length=200), nullable=True),
        sa.Column("venue_name", sa.String(length=160), nullable=False),
        sa.Column("venue_key", sa.String(length=40), nullable=True),
        sa.Column("venue_address", sa.String(length=240), nullable=True),
        sa.Column("venue_lat", sa.Float(), nullable=True),
        sa.Column("venue_lng", sa.Float(), nullable=True),
        sa.Column("distance_mi", sa.Float(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("event_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="suggested"),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source", "source_id", name="uq_event_suggestion_source"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "suggestion_id",
            sa.Integer(),
            sa.ForeignKey("event_suggestions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("performer", sa.String(length=200), nullable=True),
        sa.Column("venue_key", sa.String(length=40), nullable=False, server_default="generic"),
        sa.Column("venue_name", sa.String(length=160), nullable=False),
        sa.Column("venue_address", sa.String(length=240), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("doors_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hero_path", sa.String(length=300), nullable=True),
        sa.Column("about_text", sa.Text(), nullable=True),
        sa.Column("tips_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("event_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_events_slug", "events", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_events_slug", table_name="events")
    op.drop_table("events")
    op.drop_table("event_suggestions")
