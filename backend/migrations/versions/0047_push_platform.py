"""Native push (FCM): push_subscriptions.platform + nullable Web Push keys

Revision ID: 0047_push_platform
Revises: 0046_ride_messages
Create Date: 2026-07-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_push_platform"
down_revision = "0046_ride_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Delivery channel. Existing rows are all Web Push.
    op.add_column(
        "push_subscriptions",
        sa.Column("platform", sa.String(length=16), nullable=False, server_default="webpush"),
    )
    # FCM subscriptions have no p256dh/auth (the token lives in `endpoint`).
    op.alter_column("push_subscriptions", "p256dh", existing_type=sa.Text(), nullable=True)
    op.alter_column("push_subscriptions", "auth", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Backfill placeholder keys for any FCM rows so the NOT NULL can be restored.
    op.execute("UPDATE push_subscriptions SET p256dh = '' WHERE p256dh IS NULL")
    op.execute("UPDATE push_subscriptions SET auth = '' WHERE auth IS NULL")
    op.alter_column("push_subscriptions", "auth", existing_type=sa.Text(), nullable=False)
    op.alter_column("push_subscriptions", "p256dh", existing_type=sa.Text(), nullable=False)
    op.drop_column("push_subscriptions", "platform")
