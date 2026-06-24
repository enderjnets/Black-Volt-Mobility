"""per-user calendar OAuth credentials

Adds `calendar_credential` to store each team member's own Google Calendar
connection (refresh token encrypted at rest). Ride sync routes a member's rides
to their connected calendar; the admin keeps the shared Black Volt calendar.

Revision ID: 0023_calendar_credential
Revises: 0022_client_onboarding_profile
Create Date: 2026-06-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_calendar_credential"
down_revision: str | None = "0022_client_onboarding_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_credential",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False),
        sa.Column("google_email", sa.String(length=254), nullable=True),
        sa.Column(
            "calendar_id",
            sa.String(length=254),
            nullable=False,
            server_default="primary",
        ),
        sa.Column("scopes", sa.String(length=255), nullable=True),
        sa.Column(
            "connected_at",
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
    )
    op.create_unique_constraint(
        "uq_calendar_credential_tenant", "calendar_credential", ["tenant_id"]
    )
    op.create_index(
        "ix_calendar_credential_tenant_id", "calendar_credential", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_credential_tenant_id", table_name="calendar_credential")
    op.drop_constraint(
        "uq_calendar_credential_tenant", "calendar_credential", type_="unique"
    )
    op.drop_table("calendar_credential")
