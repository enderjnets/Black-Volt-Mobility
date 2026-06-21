"""social post render progress

Adds `social_posts.render_progress` (int 0–100) and `social_posts.render_stage`
(stage key) so the render worker can report live progress via the signed
/social/webhooks/render/progress webhook while a post is rendering; the frontend
draws a progress bar from these.

Revision ID: 0020_social_render_progress
Revises: 0019_social_reference_images
Create Date: 2026-06-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_social_render_progress"
down_revision: str | None = "0019_social_reference_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "social_posts",
        sa.Column("render_progress", sa.Integer(), nullable=True),
    )
    op.add_column(
        "social_posts",
        sa.Column("render_stage", sa.String(length=48), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("social_posts", "render_stage")
    op.drop_column("social_posts", "render_progress")
