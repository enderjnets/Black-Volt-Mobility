"""Client (passenger) notifications feed — the client bell

Revision ID: 0048_client_notifications
Revises: 0047_push_platform
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048_client_notifications"
down_revision = "0047_push_platform"
branch_labels = None
depends_on = None

CLIENT_NOTIFICATION_KIND = ("ride_message", "refund_full", "refund_partial")


def upgrade() -> None:
    # Idempotent enum create (asyncpg's checkfirst is unreliable); the table
    # references it with create_type=False so create_table won't re-emit it.
    values_sql = ", ".join(f"'{v}'" for v in CLIENT_NOTIFICATION_KIND)
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='client_notification_kind') "
        f"THEN CREATE TYPE client_notification_kind AS ENUM ({values_sql}); END IF; "
        "END $$;"
    )
    client_notification_kind = postgresql.ENUM(
        *CLIENT_NOTIFICATION_KIND, name="client_notification_kind", create_type=False
    )

    op.create_table(
        "client_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("kind", client_notification_kind, nullable=False),
        sa.Column("data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_client_notifications_client_id", "client_notifications", ["client_id"])
    op.create_index("ix_client_notifications_tenant_id", "client_notifications", ["tenant_id"])
    op.create_index("ix_client_notifications_read", "client_notifications", ["read"])
    op.create_index("ix_client_notifications_created_at", "client_notifications", ["created_at"])
    op.create_index(
        "ix_client_notifications_client_id_id", "client_notifications", ["client_id", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_client_notifications_client_id_id", table_name="client_notifications")
    op.drop_index("ix_client_notifications_created_at", table_name="client_notifications")
    op.drop_index("ix_client_notifications_read", table_name="client_notifications")
    op.drop_index("ix_client_notifications_tenant_id", table_name="client_notifications")
    op.drop_index("ix_client_notifications_client_id", table_name="client_notifications")
    op.drop_table("client_notifications")
    op.execute("DROP TYPE IF EXISTS client_notification_kind")
