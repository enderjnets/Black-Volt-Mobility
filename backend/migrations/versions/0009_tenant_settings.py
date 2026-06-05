"""tenant brand/profile settings columns

Revision ID: 0009_tenant_settings
Revises: 0008_client_lang
Create Date: 2026-06-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_tenant_settings"
down_revision: str | None = "0008_client_lang"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("website", sa.String(length=200), nullable=True))
    op.add_column("tenants", sa.Column("brand_color", sa.String(length=9), nullable=True))
    op.add_column("tenants", sa.Column("logo_path", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("photo_path", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("rating", sa.Float(), nullable=True))
    op.add_column("tenants", sa.Column("since_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "since_year")
    op.drop_column("tenants", "rating")
    op.drop_column("tenants", "photo_path")
    op.drop_column("tenants", "logo_path")
    op.drop_column("tenants", "brand_color")
    op.drop_column("tenants", "website")
    op.drop_column("tenants", "bio")
