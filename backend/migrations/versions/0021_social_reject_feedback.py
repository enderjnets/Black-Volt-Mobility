"""social reject reason + brand feedback log

Adds `social_posts.rejection_reason` (the owner's "why" when rejecting a post,
used to regenerate a corrected draft) and a new `social_feedback` table that logs
each rejection reason per tenant so the AI "learns" — the most-recent-distinct
lessons are injected into every future brief's system prompt.

Revision ID: 0021_social_reject_feedback
Revises: 0020_social_render_progress
Create Date: 2026-06-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_social_reject_feedback"
down_revision: str | None = "0020_social_render_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "social_posts",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )
    op.create_table(
        "social_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("social_feedback")
    op.drop_column("social_posts", "rejection_reason")
