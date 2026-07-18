"""Per-ride passenger<->driver messages + ride_message notification kind

Revision ID: 0046_ride_messages
Revises: 0045_ride_tip
Create Date: 2026-07-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0046_ride_messages"
down_revision = "0045_ride_tip"
branch_labels = None
depends_on = None

RIDE_MESSAGE_SENDER = ("client", "driver")


def upgrade() -> None:
    # Idempotent enum create (asyncpg's checkfirst is unreliable); the table
    # references it with create_type=False so create_table won't re-emit it.
    values_sql = ", ".join(f"'{v}'" for v in RIDE_MESSAGE_SENDER)
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='ride_message_sender') "
        f"THEN CREATE TYPE ride_message_sender AS ENUM ({values_sql}); END IF; END $$;"
    )
    ride_message_sender = postgresql.ENUM(
        *RIDE_MESSAGE_SENDER, name="ride_message_sender", create_type=False
    )

    op.create_table(
        "ride_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("ride_id", sa.Integer(), nullable=False),
        sa.Column("sender", ride_message_sender, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ride_id"], ["rides.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ride_messages_tenant_id", "ride_messages", ["tenant_id"])
    op.create_index("ix_ride_messages_ride_id", "ride_messages", ["ride_id"])
    op.create_index("ix_ride_messages_created_at", "ride_messages", ["created_at"])
    op.create_index("ix_ride_messages_ride_id_id", "ride_messages", ["ride_id", "id"])

    # Postgres forbids using an enum value in the same transaction it was added,
    # so add it in its own autocommit block. It is only ever *used* by later
    # inserts, never within this migration.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'ride_message'")


def downgrade() -> None:
    op.drop_index("ix_ride_messages_ride_id_id", table_name="ride_messages")
    op.drop_index("ix_ride_messages_created_at", table_name="ride_messages")
    op.drop_index("ix_ride_messages_ride_id", table_name="ride_messages")
    op.drop_index("ix_ride_messages_tenant_id", table_name="ride_messages")
    op.drop_table("ride_messages")
    op.execute("DROP TYPE IF EXISTS ride_message_sender")
    # The 'ride_message' value on notification_kind is intentionally left in
    # place: Postgres cannot drop a single enum value, and it is harmless once
    # ride_messages is gone (nothing references it).
