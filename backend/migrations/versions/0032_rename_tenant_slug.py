"""rename default tenant slug black-volt -> ender-ocando

Revision ID: 0032_rename_tenant_slug
Revises: 0031_legal_consents
Create Date: 2026-06-26

The public driver profile URL is derived from the tenant slug. The single-driver
MVP tenant is renamed from the brand slug to the driver's name so the shared
profile URL reads `/d/ender-ocando`. The old `black-volt` slug keeps working via
an application-level alias (see app/services/tenancy.py SLUG_ALIASES), so this
only updates the stored value; it is a no-op if the row was already renamed.
"""
from __future__ import annotations

from alembic import op

revision = "0032_rename_tenant_slug"
down_revision = "0031_legal_consents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE tenants SET slug = 'ender-ocando' "
        "WHERE slug = 'black-volt' "
        "AND NOT EXISTS (SELECT 1 FROM tenants t2 WHERE t2.slug = 'ender-ocando')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE tenants SET slug = 'black-volt' "
        "WHERE slug = 'ender-ocando' "
        "AND NOT EXISTS (SELECT 1 FROM tenants t2 WHERE t2.slug = 'black-volt')"
    )
