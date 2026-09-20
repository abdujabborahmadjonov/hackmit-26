"""recommendation bandit arms, profile weights, social/quality telemetry

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-20 11:40:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teacher_profiles",
        sa.Column(
            "recommendation_weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.add_column(
        "recommendation_events",
        sa.Column("bandit_arm_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "recommendation_events",
        sa.Column("rank_position", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_recommendation_events_bandit_arm_id",
        "recommendation_events",
        ["bandit_arm_id"],
    )

    op.create_table(
        "bandit_arms",
        sa.Column("arm_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("alpha", sa.Float(), nullable=False, server_default=sa.text("1")),
        sa.Column("beta", sa.Float(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "pulls",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
    )


def downgrade() -> None:
    op.drop_table("bandit_arms")
    op.drop_index(
        "ix_recommendation_events_bandit_arm_id", table_name="recommendation_events"
    )
    op.drop_column("recommendation_events", "rank_position")
    op.drop_column("recommendation_events", "bandit_arm_id")
    op.drop_column("teacher_profiles", "recommendation_weights")
