"""allowed_users — DB-backed access list for driver dashboard sign-in

Moves the Google Sign-In allow-list out of env vars into a table so the owner
manages who can access the dashboard (and as what) from the Team panel without a
redeploy. Each driver's tenant_id is filled on first sign-in (workspace
auto-provisioned). Bootstrap admins (GOOGLE_ADMIN_EMAILS) are seeded on startup.

Revision ID: 0011_allowed_users
Revises: 0010_client_home_address
Create Date: 2026-06-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_allowed_users"
down_revision: str | None = "0010_client_home_address"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "allowed_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="driver"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("added_by", sa.String(length=254), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_allowed_users_email", "allowed_users", ["email"], unique=True)
    op.create_index("ix_allowed_users_tenant_id", "allowed_users", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_allowed_users_tenant_id", table_name="allowed_users")
    op.drop_index("ix_allowed_users_email", table_name="allowed_users")
    op.drop_table("allowed_users")
