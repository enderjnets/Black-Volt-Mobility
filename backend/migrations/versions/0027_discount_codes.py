"""discount codes + campaigns + ride discount columns

Revision ID: 0027_discount_codes
Revises: 0026_ride_preferences_snapshot
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0027_discount_codes"
down_revision: str | None = "0026_ride_preferences_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discount_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_discount_campaigns_tenant_id", "discount_campaigns", ["tenant_id"])
    op.create_table(
        "discount_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_email", sa.String(length=255), nullable=False),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("discount_campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("code = upper(code)", name="ck_discount_codes_code_upper"),
    )
    op.create_index("ix_discount_codes_tenant_id", "discount_codes", ["tenant_id"])
    op.create_unique_constraint("uq_discount_codes_code", "discount_codes", ["code"])
    op.add_column(
        "rides",
        sa.Column(
            "discount_code_id",
            sa.Integer(),
            sa.ForeignKey("discount_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "rides",
        sa.Column("discount_amount", sa.Float(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("rides", "discount_amount")
    op.drop_column("rides", "discount_code_id")
    op.drop_constraint("uq_discount_codes_code", "discount_codes", type_="unique")
    op.drop_index("ix_discount_codes_tenant_id", table_name="discount_codes")
    op.drop_table("discount_codes")
    # IF EXISTS: older DB states may not have this index (pre-tenant_id-on-campaigns)
    op.execute("DROP INDEX IF EXISTS ix_discount_campaigns_tenant_id")
    op.drop_table("discount_campaigns")
