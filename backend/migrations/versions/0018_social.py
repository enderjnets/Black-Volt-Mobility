"""social media module

Adds the tenant-scoped social tables for the owner-approval social workflow:
`social_accounts` (connected IG/FB/TikTok + OAuth tokens), `social_posts`
(content moving draft→…→published, gated on owner approval), and
`social_interactions` (comments/DMs + AI-drafted replies).

Revision ID: 0018_social
Revises: 0017_platform_stats
Create Date: 2026-06-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_social"
down_revision: str | None = "0017_platform_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("external_account_id", sa.String(length=190), nullable=True),
        sa.Column("display_name", sa.String(length=190), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "platform", name="uq_social_account_tenant_platform"
        ),
    )
    op.create_index(
        op.f("ix_social_accounts_tenant_id"), "social_accounts", ["tenant_id"]
    )

    op.create_table(
        "social_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=True),
        sa.Column("script", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.String(length=500), nullable=True),
        sa.Column("media_path", sa.String(length=500), nullable=True),
        sa.Column("cover_path", sa.String(length=500), nullable=True),
        sa.Column("targets", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("render_job_id", sa.String(length=64), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_ids", sa.JSON(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("likes", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_social_posts_tenant_id"), "social_posts", ["tenant_id"])
    op.create_index(op.f("ix_social_posts_status"), "social_posts", ["status"])
    op.create_index(
        op.f("ix_social_posts_scheduled_at"), "social_posts", ["scheduled_at"]
    )

    op.create_table(
        "social_interactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("external_post_id", sa.String(length=190), nullable=True),
        sa.Column("external_comment_id", sa.String(length=190), nullable=True),
        sa.Column("author_handle", sa.String(length=190), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column("ai_draft", sa.Text(), nullable=True),
        sa.Column("reply_status", sa.String(length=20), nullable=False),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_social_interactions_tenant_id"), "social_interactions", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_social_interactions_post_id"), "social_interactions", ["post_id"]
    )
    op.create_index(
        op.f("ix_social_interactions_external_comment_id"),
        "social_interactions",
        ["external_comment_id"],
    )
    op.create_index(
        op.f("ix_social_interactions_reply_status"),
        "social_interactions",
        ["reply_status"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_social_interactions_reply_status"), table_name="social_interactions"
    )
    op.drop_index(
        op.f("ix_social_interactions_external_comment_id"),
        table_name="social_interactions",
    )
    op.drop_index(
        op.f("ix_social_interactions_post_id"), table_name="social_interactions"
    )
    op.drop_index(
        op.f("ix_social_interactions_tenant_id"), table_name="social_interactions"
    )
    op.drop_table("social_interactions")

    op.drop_index(op.f("ix_social_posts_scheduled_at"), table_name="social_posts")
    op.drop_index(op.f("ix_social_posts_status"), table_name="social_posts")
    op.drop_index(op.f("ix_social_posts_tenant_id"), table_name="social_posts")
    op.drop_table("social_posts")

    op.drop_index(op.f("ix_social_accounts_tenant_id"), table_name="social_accounts")
    op.drop_table("social_accounts")
