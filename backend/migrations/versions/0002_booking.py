"""booking core: rate_configs + rides

Revision ID: 0002_booking
Revises: 0001_initial
Create Date: 2026-05-31

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_booking"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RIDE_STATUS = (
    "requested",
    "quoted",
    "confirmed",
    "assigned",
    "en_route",
    "completed",
    "cancelled",
    "no_show",
)


def upgrade() -> None:
    op.create_table(
        "rate_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("minimum", sa.Float(), nullable=False, server_default="28"),
        sa.Column("base", sa.Float(), nullable=False, server_default="12"),
        sa.Column("per_mile", sa.Float(), nullable=False, server_default="2.4"),
        sa.Column("per_minute", sa.Float(), nullable=False, server_default="0.55"),
        sa.Column("airport_flat", sa.Float(), nullable=False, server_default="74"),
        sa.Column("extra_stop_fee", sa.Float(), nullable=False, server_default="15"),
        sa.Column("group_surcharge", sa.Float(), nullable=False, server_default="20"),
        sa.Column("group_threshold", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("peak_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("peak_multiplier", sa.Float(), nullable=False, server_default="1.4"),
        sa.Column("loyalty_discount_pct", sa.Float(), nullable=False, server_default="10"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", name="uq_rate_config_tenant"),
    )
    op.create_index("ix_rate_configs_tenant_id", "rate_configs", ["tenant_id"])

    # Idempotent enum create (asyncpg's checkfirst is unreliable); the table
    # references it with create_type=False so create_table won't re-emit it.
    values_sql = ", ".join(f"'{v}'" for v in RIDE_STATUS)
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='ride_status') "
        f"THEN CREATE TYPE ride_status AS ENUM ({values_sql}); END IF; END $$;"
    )
    ride_status = postgresql.ENUM(*RIDE_STATUS, name="ride_status", create_type=False)

    op.create_table(
        "rides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("status", ride_status, nullable=False, server_default="quoted"),
        sa.Column("pickup_text", sa.String(length=400), nullable=False),
        sa.Column("pickup_lat", sa.Float(), nullable=True),
        sa.Column("pickup_lng", sa.Float(), nullable=True),
        sa.Column("pickup_place_id", sa.String(length=300), nullable=True),
        sa.Column("dropoff_text", sa.String(length=400), nullable=False),
        sa.Column("dropoff_lat", sa.Float(), nullable=True),
        sa.Column("dropoff_lng", sa.Float(), nullable=True),
        sa.Column("dropoff_place_id", sa.String(length=300), nullable=True),
        sa.Column("stops", sa.JSON(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distance_miles", sa.Float(), nullable=True),
        sa.Column("duration_minutes", sa.Float(), nullable=True),
        sa.Column("fare_total", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("price_breakdown", sa.JSON(), nullable=True),
        sa.Column("pax", sa.Integer(), nullable=True),
        sa.Column("vehicle", sa.String(length=120), nullable=True),
        sa.Column("flight_number", sa.String(length=20), nullable=True),
        sa.Column("lang", sa.String(length=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("passenger_name", sa.String(length=200), nullable=True),
        sa.Column("passenger_phone", sa.String(length=40), nullable=True),
        sa.Column("payment_id", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_rides_tenant_id", "rides", ["tenant_id"])
    op.create_index("ix_rides_client_id", "rides", ["client_id"])
    op.create_index("ix_rides_status", "rides", ["status"])
    op.create_index("ix_rides_scheduled_at", "rides", ["scheduled_at"])


def downgrade() -> None:
    op.drop_table("rides")
    op.execute("DROP TYPE IF EXISTS ride_status")
    op.drop_index("ix_rate_configs_tenant_id", table_name="rate_configs")
    op.drop_table("rate_configs")
