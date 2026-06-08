"""client saved home address

Revision ID: 0010_client_home_address
Revises: 0009_tenant_settings
Create Date: 2026-06-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_client_home_address"
down_revision: str | None = "0009_tenant_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("home_address", sa.String(length=400), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "home_address")
