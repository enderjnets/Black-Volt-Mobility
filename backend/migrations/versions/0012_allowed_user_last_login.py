"""allowed_users.last_login — stamp each dashboard sign-in

Adds a nullable timestamp the auth flow updates on every successful login, so
the Team panel can show per-driver last-activity.

Revision ID: 0012_allowed_user_last_login
Revises: 0011_allowed_users
Create Date: 2026-06-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_allowed_user_last_login"
down_revision: str | None = "0011_allowed_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "allowed_users",
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("allowed_users", "last_login")
