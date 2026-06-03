"""ride payment method + paid flag (multi-method settlement)

Revision ID: 0005_payment_method
Revises: 0004_payments
Create Date: 2026-06-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_payment_method"
down_revision: str | None = "0004_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYMENT_METHOD = ("cash", "square", "venmo", "zelle", "other")


def upgrade() -> None:
    values_sql = ", ".join(f"'{v}'" for v in PAYMENT_METHOD)
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='payment_method') "
        f"THEN CREATE TYPE payment_method AS ENUM ({values_sql}); END IF; END $$;"
    )
    pm = postgresql.ENUM(*PAYMENT_METHOD, name="payment_method", create_type=False)
    op.add_column(
        "rides", sa.Column("payment_method", pm, nullable=False, server_default="cash")
    )
    op.add_column(
        "rides", sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("rides", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill: rides with a captured Square payment are paid by Square.
    op.execute(
        """
        UPDATE rides r SET payment_method='square', paid=true, paid_at=p.created_at
        FROM payments p
        WHERE p.ride_id = r.id AND p.status='captured'
        """
    )


def downgrade() -> None:
    op.drop_column("rides", "paid_at")
    op.drop_column("rides", "paid")
    op.drop_column("rides", "payment_method")
    op.execute("DROP TYPE IF EXISTS payment_method")
