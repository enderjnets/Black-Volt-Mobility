"""tenant direct-line phone

Adds an optional `phone` to tenants. Shown only to registered clients (gated
server-side in the public-profile endpoint); the owner edits it from Settings.

Revision ID: 0015_tenant_phone
Revises: 0014_subscriptions_hardening
Create Date: 2026-06-15

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_tenant_phone"
down_revision: str | None = "0014_subscriptions_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("phone", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "phone")
