"""ride google calendar event id

Revision ID: 0006_ride_calendar
Revises: 0005_payment_method
Create Date: 2026-06-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_ride_calendar"
down_revision: str | None = "0005_payment_method"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rides", sa.Column("google_event_id", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("rides", "google_event_id")
