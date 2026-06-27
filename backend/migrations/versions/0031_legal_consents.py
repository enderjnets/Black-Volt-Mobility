"""legal document consents

Revision ID: 0031_legal_consents
Revises: 0030_cancellation_fields
Create Date: 2026-06-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_legal_consents"
down_revision = "0030_cancellation_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("doc_type", sa.String(length=40), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("subject_type", sa.String(length=20), nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "allowed_user_id",
            sa.Integer(),
            sa.ForeignKey("allowed_users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("signed_name", sa.String(length=200), nullable=True),
        sa.Column("lang", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "client_id", "doc_type", "version", name="uq_consent_client_doc_ver"
        ),
        sa.UniqueConstraint(
            "allowed_user_id", "doc_type", "version", name="uq_consent_user_doc_ver"
        ),
    )
    op.create_index(
        "ix_document_consents_tenant_id", "document_consents", ["tenant_id"]
    )
    op.create_index("ix_document_consents_doc_type", "document_consents", ["doc_type"])
    op.create_index(
        "ix_document_consents_client_id", "document_consents", ["client_id"]
    )
    op.create_index(
        "ix_document_consents_allowed_user_id",
        "document_consents",
        ["allowed_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_consents_allowed_user_id", table_name="document_consents")
    op.drop_index("ix_document_consents_client_id", table_name="document_consents")
    op.drop_index("ix_document_consents_doc_type", table_name="document_consents")
    op.drop_index("ix_document_consents_tenant_id", table_name="document_consents")
    op.drop_table("document_consents")
