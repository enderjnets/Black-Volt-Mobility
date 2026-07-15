"""Add tip + tip_method to rides (gratuity recorded manually post-ride).

The tip is a nullable Float (NULL = no tip recorded) kept separate from fare_total
so it never leaks into pricing/quotes, while still counting as earnings in revenue
rollups. tip_method reuses the existing `payment_method` Postgres enum (the tip may
be paid differently than the fare), referencing it with create_type=False so the
migration does not try to recreate the type.

Revision ID: 0045_ride_tip
Revises: 0044_blog_engine
Create Date: 2026-07-15 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0045_ride_tip"
down_revision = "0044_blog_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rides", sa.Column("tip", sa.Float(), nullable=True))
    op.add_column(
        "rides",
        sa.Column(
            "tip_method",
            postgresql.ENUM(name="payment_method", create_type=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("rides", "tip_method")
    op.drop_column("rides", "tip")
