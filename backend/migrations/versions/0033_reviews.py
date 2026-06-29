"""customer reviews + review invites

Revision ID: 0033_reviews
Revises: 0032_rename_tenant_slug
Create Date: 2026-06-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_reviews"
down_revision = "0032_rename_tenant_slug"
branch_labels = None
depends_on = None

REVIEW_STATUS = ("pending", "approved", "rejected")


def upgrade() -> None:
    # review_invites first — reviews.invite_id references it.
    op.create_table(
        "review_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("ride_id", sa.Integer(), nullable=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=200), nullable=True),
        sa.Column("to_email", sa.String(length=255), nullable=True),
        sa.Column("to_phone", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ride_id"], ["rides.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_review_invites_tenant_id", "review_invites", ["tenant_id"])
    op.create_index("ix_review_invites_token", "review_invites", ["token"], unique=True)

    # Idempotent enum create (asyncpg's checkfirst is unreliable); the table
    # references it with create_type=False so create_table won't re-emit it.
    values_sql = ", ".join(f"'{v}'" for v in REVIEW_STATUS)
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='review_status') "
        f"THEN CREATE TYPE review_status AS ENUM ({values_sql}); END IF; END $$;"
    )
    review_status = postgresql.ENUM(*REVIEW_STATUS, name="review_status", create_type=False)

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("ride_id", sa.Integer(), nullable=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("invite_id", sa.Integer(), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False),
        sa.Column("author_email", sa.String(length=255), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", review_status, nullable=False, server_default="pending"),
        sa.Column("show_on_home", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="public"),
        sa.Column("owner_reply", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ride_id"], ["rides.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invite_id"], ["review_invites.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_reviews_tenant_id", "reviews", ["tenant_id"])
    op.create_index("ix_reviews_ride_id", "reviews", ["ride_id"])
    op.create_index("ix_reviews_status", "reviews", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reviews_status", table_name="reviews")
    op.drop_index("ix_reviews_ride_id", table_name="reviews")
    op.drop_index("ix_reviews_tenant_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_review_invites_token", table_name="review_invites")
    op.drop_index("ix_review_invites_tenant_id", table_name="review_invites")
    op.drop_table("review_invites")
    op.execute("DROP TYPE IF EXISTS review_status")
