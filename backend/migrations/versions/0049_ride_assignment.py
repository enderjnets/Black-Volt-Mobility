"""ride hand-off: assignment snapshot, driver payout split, internal chat channel

Revision ID: 0049_ride_assignment
Revises: 0048_client_notifications
"""

from alembic import op
import sqlalchemy as sa

revision = "0049_ride_assignment"
down_revision = "0048_client_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The money split is snapshot per ride, so changing the tenant defaults later
    # never rewrites what a past ride owed the driver.
    op.add_column("rides", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rides", sa.Column("assigned_by_email", sa.String(length=254), nullable=True))
    op.add_column("rides", sa.Column("assign_note", sa.String(length=400), nullable=True))
    op.add_column("rides", sa.Column("driver_share_pct", sa.Integer(), nullable=True))
    op.add_column("rides", sa.Column("square_fee_pct", sa.Float(), nullable=True))
    op.add_column("rides", sa.Column("square_fee_fixed_cents", sa.Integer(), nullable=True))
    op.add_column("rides", sa.Column("tax_reserve_pct", sa.Float(), nullable=True))
    op.add_column(
        "rides",
        sa.Column(
            "driver_payout_status",
            sa.String(length=16),
            nullable=False,
            server_default="unpaid",
        ),
    )
    op.add_column("rides", sa.Column("driver_paid_at", sa.DateTime(timezone=True), nullable=True))

    # Tenant-level defaults the assign dialog pre-fills (Square's published US rate).
    op.add_column(
        "rate_configs",
        sa.Column("square_fee_pct", sa.Float(), nullable=False, server_default="2.9"),
    )
    op.add_column(
        "rate_configs",
        sa.Column(
            "square_fee_fixed_cents", sa.Integer(), nullable=False, server_default="30"
        ),
    )
    # 0 by default: reserving for taxes is the owner's call, and a non-zero default
    # would silently change every existing payout number.
    op.add_column(
        "rate_configs",
        sa.Column("tax_reserve_pct", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "rate_configs",
        sa.Column("default_driver_share_pct", sa.Integer(), nullable=False, server_default="80"),
    )

    # New staff bell kind. ADD VALUE IF NOT EXISTS is idempotent and cannot run inside
    # a transaction block on older PG, so it goes through autocommit.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'ride_assigned'")

    # Staff-only conversation on a ride. Existing rows are the passenger thread.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ride_message_channel') THEN
                CREATE TYPE ride_message_channel AS ENUM ('client', 'internal');
            END IF;
        END
        $$;
        """
    )
    op.add_column(
        "ride_messages",
        sa.Column(
            "channel",
            sa.Enum("client", "internal", name="ride_message_channel", create_type=False),
            nullable=False,
            server_default="client",
        ),
    )
    op.create_index(
        "ix_ride_messages_ride_channel_id", "ride_messages", ["ride_id", "channel", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ride_messages_ride_channel_id", table_name="ride_messages")
    op.drop_column("ride_messages", "channel")
    op.execute("DROP TYPE IF EXISTS ride_message_channel")
    for col in (
        "default_driver_share_pct",
        "tax_reserve_pct",
        "square_fee_fixed_cents",
        "square_fee_pct",
    ):
        op.drop_column("rate_configs", col)
    for col in (
        "driver_paid_at",
        "driver_payout_status",
        "tax_reserve_pct",
        "square_fee_fixed_cents",
        "square_fee_pct",
        "driver_share_pct",
        "assign_note",
        "assigned_by_email",
        "assigned_at",
    ):
        op.drop_column("rides", col)
