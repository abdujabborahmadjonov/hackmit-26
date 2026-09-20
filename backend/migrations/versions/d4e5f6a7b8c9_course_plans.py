"""course plans with units, sessions, and resource/technique links

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-20 05:30:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_plans",
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.Column("class_profile_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=80), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("duration_weeks", sa.Integer(), nullable=False),
        sa.Column(
            "sessions_per_week",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("goals", sa.Text(), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column(
            "generation_inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "similar_class_ids",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
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
        sa.CheckConstraint(
            "format IN ('lecture', 'lab', 'online', 'hybrid')",
            name="course_plan_format",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="course_plan_status",
        ),
        sa.CheckConstraint("duration_weeks > 0", name="course_plan_weeks_positive"),
        sa.CheckConstraint(
            "sessions_per_week > 0", name="course_plan_sessions_positive"
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name=op.f("fk_course_plans_teacher_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_profile_id"],
            ["class_profiles.id"],
            name=op.f("fk_course_plans_class_profile_id_class_profiles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_plans")),
    )
    op.create_index("ix_course_plans_teacher_id", "course_plans", ["teacher_id"])
    op.create_index(
        "ix_course_plans_class_profile_id", "course_plans", ["class_profile_id"]
    )
    op.create_index("ix_course_plans_status", "course_plans", ["status"])

    op.create_table(
        "course_plan_units",
        sa.Column("course_plan_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("objectives", sa.Text(), nullable=True),
        sa.Column(
            "concept_labels",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
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
        sa.CheckConstraint("position >= 0", name="course_plan_unit_position"),
        sa.ForeignKeyConstraint(
            ["course_plan_id"],
            ["course_plans.id"],
            name=op.f("fk_course_plan_units_course_plan_id_course_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_plan_units")),
    )
    op.create_index(
        "ix_course_plan_units_plan_id", "course_plan_units", ["course_plan_id"]
    )

    op.create_table(
        "course_plan_sessions",
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.Column("activities_summary", sa.Text(), nullable=True),
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
        sa.CheckConstraint("position >= 0", name="course_plan_session_position"),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["course_plan_units.id"],
            name=op.f("fk_course_plan_sessions_unit_id_course_plan_units"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_plan_sessions")),
    )
    op.create_index(
        "ix_course_plan_sessions_unit_id", "course_plan_sessions", ["unit_id"]
    )

    op.create_table(
        "course_plan_items",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=20),
            server_default=sa.text("'core'"),
            nullable=False,
        ),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column("technique_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("position >= 0", name="course_plan_item_position"),
        sa.CheckConstraint(
            "role IN ('core', 'extension', 'assessment')",
            name="course_plan_item_role",
        ),
        sa.CheckConstraint(
            "resource_id IS NOT NULL OR technique_id IS NOT NULL",
            name="course_plan_item_has_link",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["course_plan_sessions.id"],
            name=op.f("fk_course_plan_items_session_id_course_plan_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_course_plan_items_resource_id_resources"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["technique_id"],
            ["techniques.id"],
            name=op.f("fk_course_plan_items_technique_id_techniques"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_plan_items")),
    )
    op.create_index(
        "ix_course_plan_items_session_id", "course_plan_items", ["session_id"]
    )
    op.create_index(
        "ix_course_plan_items_resource_id", "course_plan_items", ["resource_id"]
    )
    op.create_index(
        "ix_course_plan_items_technique_id",
        "course_plan_items",
        ["technique_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_course_plan_items_technique_id", table_name="course_plan_items")
    op.drop_index("ix_course_plan_items_resource_id", table_name="course_plan_items")
    op.drop_index("ix_course_plan_items_session_id", table_name="course_plan_items")
    op.drop_table("course_plan_items")
    op.drop_index(
        "ix_course_plan_sessions_unit_id", table_name="course_plan_sessions"
    )
    op.drop_table("course_plan_sessions")
    op.drop_index("ix_course_plan_units_plan_id", table_name="course_plan_units")
    op.drop_table("course_plan_units")
    op.drop_index("ix_course_plans_status", table_name="course_plans")
    op.drop_index("ix_course_plans_class_profile_id", table_name="course_plans")
    op.drop_index("ix_course_plans_teacher_id", table_name="course_plans")
    op.drop_table("course_plans")
