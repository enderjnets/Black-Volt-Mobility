"""Web Push subscriptions + ride pickup-reminder marker

Revision ID: 0041_push_subscriptions
Revises: 0040_notifications
Create Date: 2026-07-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_push_subscriptions"
down_revision = "0040_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("ua", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_tenant_id", "push_subscriptions", ["tenant_id"]
    )
    op.create_index("ix_push_subscriptions_audience", "push_subscriptions", ["audience"])
    op.create_index(
        "ix_push_subscriptions_client_id", "push_subscriptions", ["client_id"]
    )

    # Dedup marker so the pickup-reminder job never double-pushes a ride.
    op.add_column(
        "rides",
        sa.Column("pickup_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rides", "pickup_reminder_sent_at")
    op.drop_index("ix_push_subscriptions_client_id", table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_audience", table_name="push_subscriptions")
    op.drop_index("ix_push_subscriptions_tenant_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
