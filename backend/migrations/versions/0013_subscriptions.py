"""subscriptions — driver Square subscriptions (SaaS plans)

Adds the `subscriptions` table: a tenant-scoped record of a driver's recurring
Square subscription to a Black Volt plan (e.g. Operator). An active row marks the
tenant as paid (unlocks AI features + public profile).

Revision ID: 0013_subscriptions
Revises: 0012_allowed_user_last_login
Create Date: 2026-06-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_subscriptions"
down_revision: str | None = "0012_allowed_user_last_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = sa.Enum("active", "past_due", "canceled", name="subscription_status")


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("plan_key", sa.String(length=40), nullable=False),
        sa.Column("status", _STATUS, nullable=False, server_default="active"),
        sa.Column("square_subscription_id", sa.String(length=120), nullable=True),
        sa.Column("square_customer_id", sa.String(length=120), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index("ix_subscriptions_email", "subscriptions", ["email"])
    op.create_index("ix_subscriptions_plan_key", "subscriptions", ["plan_key"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index(
        "ix_subscriptions_square_subscription_id",
        "subscriptions",
        ["square_subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_square_subscription_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_plan_key", table_name="subscriptions")
    op.drop_index("ix_subscriptions_email", table_name="subscriptions")
    op.drop_index("ix_subscriptions_tenant_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    sa.Enum(name="subscription_status").drop(op.get_bind(), checkfirst=True)
