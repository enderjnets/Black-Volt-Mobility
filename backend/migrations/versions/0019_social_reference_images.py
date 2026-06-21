"""social post reference images

Adds `social_posts.reference_image_paths` (JSON list of rel media paths) so the
owner can attach uploaded images (vehicles, backgrounds…) to a post; the render
worker animates them (Hailuo i2v / Ken Burns) into the video.

Revision ID: 0019_social_reference_images
Revises: 0018_social
Create Date: 2026-06-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_social_reference_images"
down_revision: str | None = "0018_social"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "social_posts",
        sa.Column(
            "reference_image_paths",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("social_posts", "reference_image_paths")
