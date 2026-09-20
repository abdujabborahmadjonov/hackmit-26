"""class profiles, concepts, techniques, and technique ratings

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-19 23:10:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "class_profiles",
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=80), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'planned'"), nullable=False),
        sa.Column("class_size", sa.Integer(), nullable=True),
        sa.Column("class_size_min", sa.Integer(), nullable=True),
        sa.Column("class_size_max", sa.Integer(), nullable=True),
        sa.Column("student_background", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("class_length_minutes", sa.Integer(), nullable=True),
        sa.Column("technology", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            name="class_profile_format",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'active', 'archived')",
            name="class_profile_status",
        ),
        sa.CheckConstraint(
            "class_size IS NULL OR class_size > 0",
            name="class_profile_size_positive",
        ),
        sa.CheckConstraint(
            "class_size_min IS NULL OR class_size_min > 0",
            name="class_profile_size_min_positive",
        ),
        sa.CheckConstraint(
            "class_size_max IS NULL OR class_size_max > 0",
            name="class_profile_size_max_positive",
        ),
        sa.CheckConstraint(
            "class_size_min IS NULL OR class_size_max IS NULL OR class_size_min <= class_size_max",
            name="class_profile_size_range_order",
        ),
        sa.CheckConstraint(
            "class_length_minutes IS NULL OR class_length_minutes > 0",
            name="class_profile_length_positive",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name=op.f("fk_class_profiles_teacher_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_profiles")),
    )
    op.create_index("ix_class_profiles_teacher_id", "class_profiles", ["teacher_id"])
    op.create_index("ix_class_profiles_status", "class_profiles", ["status"])
    op.create_index("ix_class_profiles_subject", "class_profiles", ["subject"])

    op.create_table(
        "concepts",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("embedding", Vector(dim=384), nullable=True),
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
            ["parent_id"],
            ["concepts.id"],
            name=op.f("fk_concepts_parent_id_concepts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concepts")),
        sa.UniqueConstraint("slug", name=op.f("uq_concepts_slug")),
    )
    op.create_index("ix_concepts_subject", "concepts", ["subject"])
    op.create_index("ix_concepts_label", "concepts", ["label"])
    op.execute(
        "CREATE INDEX ix_concepts_embedding_hnsw ON concepts "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "concept_aliases",
        sa.Column("concept_id", sa.UUID(), nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("alias_norm", sa.String(length=200), nullable=False),
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
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_aliases_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_aliases")),
        sa.UniqueConstraint("alias_norm", name="uq_concept_aliases_alias_norm"),
    )
    op.create_index("ix_concept_aliases_concept_id", "concept_aliases", ["concept_id"])
    op.create_index("ix_concept_aliases_alias_norm", "concept_aliases", ["alias_norm"])

    op.create_table(
        "techniques",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("materials", sa.Text(), nullable=True),
        sa.Column("class_time_minutes", sa.Integer(), nullable=True),
        sa.Column("teaching_style", sa.String(length=80), nullable=True),
        sa.Column("context_subject", sa.String(length=80), nullable=True),
        sa.Column("context_level", sa.String(length=50), nullable=True),
        sa.Column("context_format", sa.String(length=20), nullable=True),
        sa.Column("context_class_size", sa.Integer(), nullable=True),
        sa.Column("context_notes", sa.Text(), nullable=True),
        sa.Column(
            "problem_types",
            sa.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("is_draft", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("average_rating", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("rating_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("embedding", Vector(dim=384), nullable=True),
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
            "class_time_minutes IS NULL OR class_time_minutes > 0",
            name="technique_time_positive",
        ),
        sa.CheckConstraint(
            "context_class_size IS NULL OR context_class_size > 0",
            name="technique_context_size_positive",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_techniques_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_techniques")),
    )
    op.create_index("ix_techniques_owner_id", "techniques", ["owner_id"])
    op.create_index("ix_techniques_context_subject", "techniques", ["context_subject"])
    op.create_index(
        "ix_techniques_problem_types",
        "techniques",
        ["problem_types"],
        postgresql_using="gin",
    )
    op.create_index("ix_techniques_average_rating", "techniques", ["average_rating"])
    op.create_index("ix_techniques_is_published", "techniques", ["is_published"])
    op.execute(
        "CREATE INDEX ix_techniques_embedding_hnsw ON techniques "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "technique_concepts",
        sa.Column("technique_id", sa.UUID(), nullable=False),
        sa.Column("concept_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_technique_concepts_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["technique_id"],
            ["techniques.id"],
            name=op.f("fk_technique_concepts_technique_id_techniques"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("technique_id", "concept_id", name="pk_technique_concepts"),
    )
    op.create_index("ix_technique_concepts_concept_id", "technique_concepts", ["concept_id"])

    op.create_table(
        "rating_links",
        sa.Column("technique_id", sa.UUID(), nullable=False),
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.Column("class_profile_id", sa.UUID(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            ["class_profile_id"],
            ["class_profiles.id"],
            name=op.f("fk_rating_links_class_profile_id_class_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name=op.f("fk_rating_links_teacher_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["technique_id"],
            ["techniques.id"],
            name=op.f("fk_rating_links_technique_id_techniques"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rating_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_rating_links_token_hash")),
    )
    op.create_index("ix_rating_links_technique_id", "rating_links", ["technique_id"])
    op.create_index("ix_rating_links_teacher_id", "rating_links", ["teacher_id"])
    op.create_index("ix_rating_links_expires_at", "rating_links", ["expires_at"])

    op.create_table(
        "technique_ratings",
        sa.Column("technique_id", sa.UUID(), nullable=False),
        sa.Column("class_profile_id", sa.UUID(), nullable=True),
        sa.Column("rating_link_id", sa.UUID(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("context_subject", sa.String(length=80), nullable=True),
        sa.Column("context_level", sa.String(length=50), nullable=True),
        sa.Column("context_format", sa.String(length=20), nullable=True),
        sa.Column("context_class_size", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="technique_rating_range"),
        sa.ForeignKeyConstraint(
            ["class_profile_id"],
            ["class_profiles.id"],
            name=op.f("fk_technique_ratings_class_profile_id_class_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rating_link_id"],
            ["rating_links.id"],
            name=op.f("fk_technique_ratings_rating_link_id_rating_links"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["technique_id"],
            ["techniques.id"],
            name=op.f("fk_technique_ratings_technique_id_techniques"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_technique_ratings")),
    )
    op.create_index("ix_technique_ratings_technique_id", "technique_ratings", ["technique_id"])
    op.create_index(
        "ix_technique_ratings_class_profile_id",
        "technique_ratings",
        ["class_profile_id"],
    )


def downgrade() -> None:
    op.drop_table("technique_ratings")
    op.drop_table("rating_links")
    op.drop_table("technique_concepts")
    op.execute("DROP INDEX IF EXISTS ix_techniques_embedding_hnsw")
    op.drop_table("techniques")
    op.drop_table("concept_aliases")
    op.execute("DROP INDEX IF EXISTS ix_concepts_embedding_hnsw")
    op.drop_table("concepts")
    op.drop_table("class_profiles")
