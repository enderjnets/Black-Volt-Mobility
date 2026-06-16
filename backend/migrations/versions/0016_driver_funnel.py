"""driver sales-funnel logs + goals

Adds two tenant-scoped tables backing the "My Stats" tab:
- driver_funnel_logs: one row per driver per day (conversations/pitches/contacts).
- driver_goals: one row per driver (revenue/client targets + working days).

Revision ID: 0016_driver_funnel
Revises: 0015_tenant_phone
Create Date: 2026-06-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_driver_funnel"
down_revision: str | None = "0015_tenant_phone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "driver_funnel_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("conversations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pitches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "log_date", name="uq_funnel_log_tenant_day"),
    )
    op.create_index(
        op.f("ix_driver_funnel_logs_tenant_id"),
        "driver_funnel_logs",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_driver_funnel_logs_log_date"),
        "driver_funnel_logs",
        ["log_date"],
    )

    op.create_table(
        "driver_goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("target_weekly_revenue", sa.Float(), nullable=True),
        sa.Column("target_monthly_clients", sa.Integer(), nullable=True),
        sa.Column(
            "working_days_per_week", sa.Integer(), nullable=False, server_default="5"
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_driver_goal_tenant"),
    )
    op.create_index(
        op.f("ix_driver_goals_tenant_id"), "driver_goals", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_driver_goals_tenant_id"), table_name="driver_goals")
    op.drop_table("driver_goals")
    op.drop_index(
        op.f("ix_driver_funnel_logs_log_date"), table_name="driver_funnel_logs"
    )
    op.drop_index(
        op.f("ix_driver_funnel_logs_tenant_id"), table_name="driver_funnel_logs"
    )
    op.drop_table("driver_funnel_logs")
