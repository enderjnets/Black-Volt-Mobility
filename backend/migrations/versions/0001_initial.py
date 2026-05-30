"""initial: tenants + clients

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("tagline", sa.String(length=200), nullable=True),
        sa.Column("instagram", sa.String(length=200), nullable=True),
        sa.Column("vehicle", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "google_sub", name="uq_client_tenant_google_sub"),
    )
    op.create_index("ix_clients_tenant_id", "clients", ["tenant_id"])
    op.create_index("ix_clients_google_sub", "clients", ["google_sub"])
    op.create_index("ix_clients_email", "clients", ["email"])


def downgrade() -> None:
    op.drop_table("clients")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
