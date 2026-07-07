"""Event deposit reservation: deposit/balance + auditable terms acceptance

Revision ID: 0042_event_deposit
Revises: 0041_push_subscriptions
Create Date: 2026-07-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_event_deposit"
down_revision = "0041_push_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Event deposit reservation: 1/3 charged now (deposit_cents), balance collected in person
    # (balance_due_cents). Terms acceptance recorded for audit (deposit + 48h refund policy).
    op.add_column("rides", sa.Column("deposit_cents", sa.Integer(), nullable=True))
    op.add_column("rides", sa.Column("balance_due_cents", sa.Integer(), nullable=True))
    op.add_column(
        "rides", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("rides", sa.Column("terms_version", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("rides", "terms_version")
    op.drop_column("rides", "terms_accepted_at")
    op.drop_column("rides", "balance_due_cents")
    op.drop_column("rides", "deposit_cents")
