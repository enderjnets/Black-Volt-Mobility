"""Cancellation support: rides.cancelled_at + payments.refunded_amount.

`cancelled_at` anchors the <24h cancellation-fee rule and the refund audit
trail. `refunded_amount` records the cents actually returned (enables partial
refunds, e.g. a driver keeping a 20%/30% cancellation fee).

Revision ID: 0030_cancellation_fields
Revises: 0029_ride_discount_redeemed
Create Date: 2026-06-26 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0030_cancellation_fields"
down_revision = "0029_ride_discount_redeemed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("refunded_amount", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "refunded_amount")
    op.drop_column("rides", "cancelled_at")
