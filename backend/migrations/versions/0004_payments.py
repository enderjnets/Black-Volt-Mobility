"""payments: Square payment lifecycle

Revision ID: 0004_payments
Revises: 0003_analytics
Create Date: 2026-06-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_payments"
down_revision: str | None = "0003_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYMENT_STATUS = ("authorized", "captured", "canceled", "refunded", "failed")


def upgrade() -> None:
    # Idempotent enum create (asyncpg checkfirst is unreliable); table references
    # it with create_type=False so create_table won't re-emit it.
    values_sql = ", ".join(f"'{v}'" for v in PAYMENT_STATUS)
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='payment_status') "
        f"THEN CREATE TYPE payment_status AS ENUM ({values_sql}); END IF; END $$;"
    )
    payment_status = postgresql.ENUM(*PAYMENT_STATUS, name="payment_status", create_type=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("ride_id", sa.Integer(), nullable=True),
        sa.Column("status", payment_status, nullable=False, server_default="authorized"),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("square_payment_id", sa.String(length=120), nullable=True),
        sa.Column("square_refund_id", sa.String(length=120), nullable=True),
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ride_id"], ["rides.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_index("ix_payments_ride_id", "payments", ["ride_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_square_payment_id", "payments", ["square_payment_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.execute("DROP TYPE IF EXISTS payment_status")
