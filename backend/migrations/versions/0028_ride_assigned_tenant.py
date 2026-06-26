"""add assigned_tenant_id to rides for cross-tenant discount handoff

Revision ID: 0028_ride_assigned_tenant
Revises: 0027_discount_codes
Create Date: 2026-06-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0028_ride_assigned_tenant"
down_revision: str | None = "0027_discount_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rides",
        sa.Column(
            "assigned_tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_rides_assigned_tenant_id", "rides", ["assigned_tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_rides_assigned_tenant_id", table_name="rides")
    op.drop_column("rides", "assigned_tenant_id")
