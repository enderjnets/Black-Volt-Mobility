"""add 'gps' to the segment_source enum (Task 15, Addendum A)

Revision ID: 0051_segment_source_gps
Revises: 0050_demand_phase1
"""

from alembic import op

revision = "0051_segment_source_gps"
down_revision = "0050_demand_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE segment_source ADD VALUE IF NOT EXISTS 'gps'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value (would require rebuilding the type
    # and every column/index that uses it); no-op is the documented rollback.
    pass
