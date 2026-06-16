"""platform stats imports

Adds the tenant-scoped `platform_stats` table — Uber/Lyft/Co-op earnings
summaries read from an uploaded screenshot by the AI vision model, stored for the
My Stats platform-income panel and the platform-vs-private comparison.

Revision ID: 0017_platform_stats
Revises: 0016_driver_funnel
Create Date: 2026-06-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_platform_stats"
down_revision: str | None = "0016_driver_funnel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False, server_default="other"),
        sa.Column("period_label", sa.String(length=80), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("trips", sa.Integer(), nullable=True),
        sa.Column("earnings", sa.Float(), nullable=True),
        sa.Column("online_hours", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_stats_tenant_id"), "platform_stats", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_platform_stats_period_end"), "platform_stats", ["period_end"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_platform_stats_period_end"), table_name="platform_stats")
    op.drop_index(op.f("ix_platform_stats_tenant_id"), table_name="platform_stats")
    op.drop_table("platform_stats")
