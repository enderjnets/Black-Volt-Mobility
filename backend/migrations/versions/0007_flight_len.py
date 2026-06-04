"""widen rides.flight_number to 40 (airline name + number)

Revision ID: 0007_flight_len
Revises: 0006_ride_calendar
Create Date: 2026-06-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_flight_len"
down_revision: str | None = "0006_ride_calendar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "rides",
        "flight_number",
        existing_type=sa.String(length=20),
        type_=sa.String(length=40),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "rides",
        "flight_number",
        existing_type=sa.String(length=40),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
