"""where-to-wait phase 1: uber export, shift log, priors, flight baseline, scores

Revision ID: 0050_demand_phase1
Revises: 0049_ride_assignment
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050_demand_phase1"
down_revision = "0049_ride_assignment"
branch_labels = None
depends_on = None

_PRODUCT = ("black_suv", "black", "comfort", "x", "xl", "other")
_STATE = ("open", "enroute", "ontrip", "offline")
_SOURCE = ("export", "live")


def _enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in (
        ("uber_product", _PRODUCT),
        ("earner_state", _STATE),
        ("segment_source", _SOURCE),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    def _tenant_fk() -> sa.ForeignKey:
        # A ForeignKey instance can only be bound to one Column, so each of the
        # six tenant-scoped tables below needs its own fresh instance.
        return sa.ForeignKey("tenants.id", ondelete="CASCADE")

    op.create_table(
        "uber_trips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), _tenant_fk(), nullable=False),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("product", _enum("uber_product", _PRODUCT), nullable=False),
        sa.Column("product_raw", sa.String(80), nullable=True),
        sa.Column("request_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("begin_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dropoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("begin_lat", sa.Float(), nullable=True),
        sa.Column("begin_lng", sa.Float(), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("is_airport", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_scheduled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("fare_total", sa.Numeric(10, 2), nullable=True),
        sa.Column("surge_multiplier", sa.Numeric(5, 2), nullable=True),
        sa.Column("distance_mi", sa.Numeric(8, 2), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "dedup_key", name="uq_uber_trips_dedup"),
    )
    op.create_index("ix_uber_trips_tenant_id", "uber_trips", ["tenant_id"])
    op.create_index("ix_uber_trips_begin_at", "uber_trips", ["begin_at"])

    op.create_table(
        "driver_state_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), _tenant_fk(), nullable=False),
        sa.Column("dedup_key", sa.String(80), nullable=False),
        sa.Column("state", _enum("earner_state", _STATE), nullable=False),
        sa.Column("begin_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("begin_lat", sa.Float(), nullable=True),
        sa.Column("begin_lng", sa.Float(), nullable=True),
        sa.Column("end_lat", sa.Float(), nullable=True),
        sa.Column("end_lng", sa.Float(), nullable=True),
        sa.Column("h3_r8", sa.String(16), nullable=True),
        sa.Column("zone_key", sa.String(40), nullable=True),
        sa.Column("source", _enum("segment_source", _SOURCE), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "dedup_key", name="uq_driver_state_segments_dedup"),
    )
    op.create_index("ix_driver_state_segments_tenant_id", "driver_state_segments", ["tenant_id"])
    op.create_index("ix_driver_state_segments_begin_at", "driver_state_segments", ["begin_at"])
    op.create_index("ix_driver_state_segments_h3_r8", "driver_state_segments", ["h3_r8"])

    op.create_table(
        "offer_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), _tenant_fk(), nullable=False),
        sa.Column("client_event_id", sa.String(64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("h3_r8", sa.String(16), nullable=True),
        sa.Column("product", _enum("uber_product", _PRODUCT), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fare", sa.Numeric(10, 2), nullable=True),
        sa.Column("dest_text", sa.String(200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "client_event_id", name="uq_offer_events_client_event"),
    )
    op.create_index("ix_offer_events_tenant_id", "offer_events", ["tenant_id"])
    op.create_index("ix_offer_events_at", "offer_events", ["at"])
    op.create_index("ix_offer_events_h3_r8", "offer_events", ["h3_r8"])

    op.create_table(
        "dispatch_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), _tenant_fk(), nullable=False),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes_online", sa.Float(), nullable=False, server_default="0"),
        sa.Column("minutes_active", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dispatches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expireds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_trips", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "dedup_key", name="uq_dispatch_windows_dedup"),
    )
    op.create_index("ix_dispatch_windows_tenant_id", "dispatch_windows", ["tenant_id"])
    op.create_index("ix_dispatch_windows_window_start", "dispatch_windows", ["window_start"])

    op.create_table(
        "demand_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), _tenant_fk(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("summary", sa.JSON(), nullable=False),
    )
    op.create_index("ix_demand_imports_tenant_id", "demand_imports", ["tenant_id"])

    op.create_table(
        "hex_priors",
        sa.Column("h3_r8", sa.String(16), primary_key=True),
        sa.Column("affluence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hotels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generators", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("den_distance_mi", sa.Float(), nullable=False, server_default="0"),
        sa.Column("zone_key", sa.String(40), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_hex_priors_zone_key", "hex_priors", ["zone_key"])

    op.create_table(
        "den_flight_baseline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("dow", sa.Integer(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("departures", sa.Float(), nullable=False, server_default="0"),
        sa.Column("arrivals", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_period", sa.String(40), nullable=True),
        sa.UniqueConstraint("month", "dow", "hour", name="uq_den_flight_baseline"),
    )

    for name in ("week_scores", "hex_scores"):
        cols = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), _tenant_fk(), nullable=False),
            sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        ]
        if name == "week_scores":
            cols += [
                sa.Column("zone_key", sa.String(40), nullable=False),
                sa.Column("dow", sa.Integer(), nullable=False),
                sa.Column("hour", sa.Integer(), nullable=False),
            ]
        else:
            cols += [
                sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
                sa.Column("h3_r8", sa.String(16), nullable=False),
            ]
        cols += [
            sa.Column("mean", sa.Float(), nullable=False),
            sa.Column("lo", sa.Float(), nullable=False),
            sa.Column("hi", sa.Float(), nullable=False),
            sa.Column("own_share", sa.Float(), nullable=False),
            sa.Column("reasons", sa.JSON(), nullable=True),
        ]
        op.create_table(name, *cols)
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index("ix_week_scores_zone_key", "week_scores", ["zone_key"])
    op.create_index("ix_hex_scores_slot_start", "hex_scores", ["slot_start"])

    op.add_column("rate_configs", sa.Column("bridge_fare", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("rate_configs", "bridge_fare")
    for name in (
        "hex_scores",
        "week_scores",
        "den_flight_baseline",
        "hex_priors",
        "demand_imports",
        "dispatch_windows",
        "offer_events",
        "driver_state_segments",
        "uber_trips",
    ):
        op.drop_table(name)
    bind = op.get_bind()
    for name in ("segment_source", "earner_state", "uber_product"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
