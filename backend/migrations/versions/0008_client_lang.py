"""client preferred language

Revision ID: 0008_client_lang
Revises: 0007_flight_len
Create Date: 2026-06-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_client_lang"
down_revision: str | None = "0007_flight_len"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("lang", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "lang")
