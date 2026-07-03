"""per-event pricing fields + round-trip ride linkage

Revision ID: 0038_event_pricing
Revises: 0037_events
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_event_pricing"
down_revision = "0037_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("event_fee", sa.Float(), nullable=False, server_default="0"))
    op.add_column("events", sa.Column("night_fee", sa.Float(), nullable=False, server_default="25"))
    op.add_column(
        "events",
        sa.Column("night_cutoff", sa.String(length=5), nullable=False, server_default="21:00"),
    )
    op.add_column(
        "events",
        sa.Column("wait_fee_per_hour", sa.Float(), nullable=False, server_default="30"),
    )
    op.add_column(
        "events",
        sa.Column("est_duration_hours", sa.Float(), nullable=False, server_default="3"),
    )
    op.add_column("events", sa.Column("round_trip_price", sa.Float(), nullable=True))
    op.add_column("events", sa.Column("pricing_research", sa.JSON(), nullable=True))

    # Round-trip linkage on the outbound ride.
    op.add_column(
        "rides",
        sa.Column("return_ride_id", sa.Integer(), sa.ForeignKey("rides.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.add_column(
        "rides",
        sa.Column("is_return", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("rides", "is_return")
    op.drop_column("rides", "return_ride_id")
    op.drop_column("events", "pricing_research")
    op.drop_column("events", "round_trip_price")
    op.drop_column("events", "est_duration_hours")
    op.drop_column("events", "wait_fee_per_hour")
    op.drop_column("events", "night_cutoff")
    op.drop_column("events", "night_fee")
    op.drop_column("events", "event_fee")
