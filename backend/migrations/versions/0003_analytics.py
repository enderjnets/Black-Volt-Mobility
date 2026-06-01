"""analytics: first-party usage events

Revision ID: 0003_analytics
Revises: 0002_booking
Create Date: 2026-06-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_analytics"
down_revision: str | None = "0002_booking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("visitor_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("path", sa.String(length=400), nullable=True),
        sa.Column("referrer", sa.String(length=400), nullable=True),
        sa.Column("utm_source", sa.String(length=120), nullable=True),
        sa.Column("utm_medium", sa.String(length=120), nullable=True),
        sa.Column("utm_campaign", sa.String(length=120), nullable=True),
        sa.Column("device", sa.String(length=12), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("props", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_analytics_events_tenant_id", "analytics_events", ["tenant_id"])
    op.create_index("ix_analytics_events_visitor_id", "analytics_events", ["visitor_id"])
    op.create_index("ix_analytics_events_session_id", "analytics_events", ["session_id"])
    op.create_index("ix_analytics_events_client_id", "analytics_events", ["client_id"])
    op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])
    op.create_index(
        "ix_analytics_tenant_created", "analytics_events", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_analytics_tenant_type", "analytics_events", ["tenant_id", "event_type"]
    )


def downgrade() -> None:
    op.drop_table("analytics_events")
