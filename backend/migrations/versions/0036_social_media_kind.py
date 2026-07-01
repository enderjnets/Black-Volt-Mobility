"""social post media_kind + tenant daily media preference

Revision ID: 0036_social_media_kind
Revises: 0035_rate_zone_prices
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_social_media_kind"
down_revision = "0035_rate_zone_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "social_posts",
        sa.Column("media_kind", sa.String(length=8), nullable=False, server_default="video"),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "social_daily_media", sa.String(length=8), nullable=False, server_default="video"
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "social_daily_media")
    op.drop_column("social_posts", "media_kind")
