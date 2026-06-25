"""Saved address book (client_addresses) + email_consent preference.

Backs the /account overhaul: passengers manage multiple labeled addresses with
one default, and an email-notification consent toggle alongside sms_consent.

Revision ID: 0024_client_address_and_consent
Revises: 0023_calendar_credential
Create Date: 2026-06-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0024_client_address_and_consent"
down_revision: str | None = "0023_calendar_credential"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("address", sa.String(length=400), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_client_addresses_tenant_id", "client_addresses", ["tenant_id"])
    op.create_index("ix_client_addresses_client_id", "client_addresses", ["client_id"])
    op.add_column(
        "clients",
        sa.Column("email_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("clients", "email_consent")
    op.drop_index("ix_client_addresses_client_id", table_name="client_addresses")
    op.drop_index("ix_client_addresses_tenant_id", table_name="client_addresses")
    op.drop_table("client_addresses")
