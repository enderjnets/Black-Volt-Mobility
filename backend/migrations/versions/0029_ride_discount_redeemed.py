"""Add discount_redeemed flag to rides (deferred redemption at payment time).

Revision ID: 0029_ride_discount_redeemed
Revises: 0028_ride_assigned_tenant
Create Date: 2026-06-25 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0029_ride_discount_redeemed"
down_revision = "0028_ride_assigned_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column(
            "discount_redeemed",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("rides", "discount_redeemed")
