"""In-app staff notifications (dashboard bell)

Revision ID: 0040_notifications
Revises: 0039_chat
Create Date: 2026-07-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_notifications"
down_revision = "0039_chat"
branch_labels = None
depends_on = None

NOTIFICATION_KIND = (
    "ride_new",
    "ride_cancelled",
    "chat_escalated",
    "chat_message",
    "review_new",
    "discount_redeemed",
    "subscription_payment_failed",
)


def upgrade() -> None:
    # Idempotent enum create (asyncpg's checkfirst is unreliable); the table
    # references it with create_type=False so create_table won't re-emit it.
    values_sql = ", ".join(f"'{v}'" for v in NOTIFICATION_KIND)
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='notification_kind') "
        f"THEN CREATE TYPE notification_kind AS ENUM ({values_sql}); END IF; END $$;"
    )
    notification_kind = postgresql.ENUM(
        *NOTIFICATION_KIND, name="notification_kind", create_type=False
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("kind", notification_kind, nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_read", "notifications", ["read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index(
        "ix_notifications_tenant_created",
        "notifications",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_tenant_created", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_read", table_name="notifications")
    op.drop_index("ix_notifications_tenant_id", table_name="notifications")
    op.drop_table("notifications")
    op.execute("DROP TYPE IF EXISTS notification_kind")
