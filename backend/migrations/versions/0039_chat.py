"""Joules chatbot: conversations + messages

Revision ID: 0039_chat
Revises: 0038_event_pricing
Create Date: 2026-07-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_chat"
down_revision = "0038_event_pricing"
branch_labels = None
depends_on = None

CHAT_STATUS = ("open", "escalated", "closed")
CHAT_ROLE = ("user", "assistant", "owner")


def upgrade() -> None:
    # Idempotent enum creates (asyncpg's checkfirst is unreliable); tables
    # reference them with create_type=False so create_table won't re-emit them.
    for name, values in (("chat_status", CHAT_STATUS), ("chat_role", CHAT_ROLE)):
        values_sql = ", ".join(f"'{v}'" for v in values)
        op.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='{name}') "
            f"THEN CREATE TYPE {name} AS ENUM ({values_sql}); END IF; END $$;"
        )
    chat_status = postgresql.ENUM(*CHAT_STATUS, name="chat_status", create_type=False)
    chat_role = postgresql.ENUM(*CHAT_ROLE, name="chat_role", create_type=False)

    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("status", chat_status, nullable=False, server_default="open"),
        sa.Column("lang", sa.String(length=2), nullable=True),
        sa.Column("unread_for_staff", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "client_id", name="uq_chat_conv_tenant_client"),
    )
    op.create_index("ix_chat_conversations_tenant_id", "chat_conversations", ["tenant_id"])
    op.create_index("ix_chat_conversations_client_id", "chat_conversations", ["client_id"])
    op.create_index("ix_chat_conversations_status", "chat_conversations", ["status"])
    op.create_index(
        "ix_chat_conversations_tenant_last",
        "chat_conversations",
        ["tenant_id", "last_message_at"],
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", chat_role, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_chat_messages_tenant_id", "chat_messages", ["tenant_id"])
    op.create_index(
        "ix_chat_messages_conversation", "chat_messages", ["conversation_id", "id"]
    )
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_conversation", table_name="chat_messages")
    op.drop_index("ix_chat_messages_tenant_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_conversations_tenant_last", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_status", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_client_id", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_tenant_id", table_name="chat_conversations")
    op.drop_table("chat_conversations")
    op.execute("DROP TYPE IF EXISTS chat_role")
    op.execute("DROP TYPE IF EXISTS chat_status")
