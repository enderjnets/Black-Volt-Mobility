"""Client standing ride preferences (ride_preferences JSONB).

Backs the /account "Ride preferences" panel and the onboarding gate: the
passenger stores standing defaults (conversation, temperature, music, luggage
help, pet/service animal, free-text notes) that the driver sees on the ride
detail. JSONB so the option set can grow without a schema migration; the shape
is validated by the RidePreferences schema in services/profile.py.

Revision ID: 0025_ride_preferences
Revises: 0024_client_address_and_consent
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_ride_preferences"
down_revision: str | None = "0024_client_address_and_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column(
            "ride_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "ride_preferences")
