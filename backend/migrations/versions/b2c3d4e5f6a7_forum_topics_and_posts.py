"""forum topics and posts

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-19 21:30:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forum_topics",
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("reply_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_forum_topics_author_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forum_topics")),
    )
    op.create_index("ix_forum_topics_last_activity", "forum_topics", ["last_activity_at"])
    op.create_index("ix_forum_topics_author_id", "forum_topics", ["author_id"])
    op.create_index("ix_forum_topics_category", "forum_topics", ["category"])

    op.create_table(
        "forum_posts",
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["forum_topics.id"],
            name=op.f("fk_forum_posts_topic_id_forum_topics"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_forum_posts_author_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forum_posts")),
    )
    op.create_index("ix_forum_posts_topic_created", "forum_posts", ["topic_id", "created_at"])
    op.create_index("ix_forum_posts_author_id", "forum_posts", ["author_id"])


def downgrade() -> None:
    op.drop_index("ix_forum_posts_author_id", table_name="forum_posts")
    op.drop_index("ix_forum_posts_topic_created", table_name="forum_posts")
    op.drop_table("forum_posts")
    op.drop_index("ix_forum_topics_category", table_name="forum_topics")
    op.drop_index("ix_forum_topics_author_id", table_name="forum_topics")
    op.drop_index("ix_forum_topics_last_activity", table_name="forum_topics")
    op.drop_table("forum_topics")
