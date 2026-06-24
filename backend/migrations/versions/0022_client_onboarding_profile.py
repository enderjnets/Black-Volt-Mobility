"""client onboarding profile fields

Adds structured first/last name (prefilled from Google given_name/family_name)
and an SMS-consent flag to `clients`, supporting the post-Google-login profile
gate on /book. `name` stays as the display/full name, kept in sync server-side.

Revision ID: 0022_client_onboarding_profile
Revises: 0021_social_reject_feedback
Create Date: 2026-06-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_client_onboarding_profile"
down_revision: str | None = "0021_social_reject_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("first_name", sa.String(length=120), nullable=True))
    op.add_column("clients", sa.Column("last_name", sa.String(length=120), nullable=True))
    op.add_column(
        "clients",
        sa.Column("sms_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("clients", "sms_consent")
    op.drop_column("clients", "last_name")
    op.drop_column("clients", "first_name")
