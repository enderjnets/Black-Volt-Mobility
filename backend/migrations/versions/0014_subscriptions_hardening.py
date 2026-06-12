"""subscriptions hardening — pending status + open-subscription uniqueness

Adds the 'pending' enum value (Square create may return a not-yet-charged
subscription), normalizes existing emails to lowercase, and replaces the
low-cardinality plan_key/status indexes with a partial UNIQUE index that makes
the database own the "one open subscription per email+plan" invariant (the
app-level SELECT-then-INSERT can race under concurrent requests).

Revision ID: 0014_subscriptions_hardening
Revises: 0013_subscriptions
Create Date: 2026-06-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_subscriptions_hardening"
down_revision: str | None = "0013_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Allowed inside a transaction since PG12 as long as the new value isn't
    # used in the same transaction (it isn't).
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'pending'")
    op.execute("UPDATE subscriptions SET email = lower(trim(email))")
    op.drop_index("ix_subscriptions_plan_key", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.create_index(
        "uq_subscriptions_email_plan_open",
        "subscriptions",
        ["email", "plan_key"],
        unique=True,
        postgresql_where=sa.text("status != 'canceled'"),
    )


def downgrade() -> None:
    op.drop_index("uq_subscriptions_email_plan_open", table_name="subscriptions")
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_plan_key", "subscriptions", ["plan_key"])
    # Postgres cannot remove an enum value; 'pending' stays behind (harmless).
