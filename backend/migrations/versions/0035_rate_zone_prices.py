"""per-tenant flat-rate zone price overrides

Revision ID: 0035_rate_zone_prices
Revises: 0034_review_reminders
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_rate_zone_prices"
down_revision = "0034_review_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rate_configs",
        sa.Column("zone_prices", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rate_configs", "zone_prices")
