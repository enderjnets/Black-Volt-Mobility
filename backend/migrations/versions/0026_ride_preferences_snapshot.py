"""Per-ride preference snapshot (rides.ride_preferences JSON).

A ride carries its own preference snapshot, taken from the client's standing
preferences at booking time but editable per ride. Nullable: null means none
were specified (display falls back to the client's standing preferences). JSON
to match the other free-form ride columns (stops, price_breakdown).

Revision ID: 0026_ride_preferences_snapshot
Revises: 0025_ride_preferences
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0026_ride_preferences_snapshot"
down_revision: str | None = "0025_ride_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rides", sa.Column("ride_preferences", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("rides", "ride_preferences")
