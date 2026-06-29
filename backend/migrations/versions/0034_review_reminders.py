"""per-tenant auto review-reminder settings

Revision ID: 0034_review_reminders
Revises: 0033_reviews
Create Date: 2026-06-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_review_reminders"
down_revision = "0033_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "review_reminders_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "review_reminder_hours",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "review_reminder_hours")
    op.drop_column("tenants", "review_reminders_enabled")
