"""student verified ratings and tokens

Revision ID: a1b2c3d4e5f6
Revises: f37b766f11e4
Create Date: 2026-09-19 20:10:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f37b766f11e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_verification_tokens",
        sa.Column("teacher_id", sa.UUID(), nullable=False),
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
            ["teacher_id"],
            ["users.id"],
            name=op.f("fk_student_verification_tokens_teacher_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_verification_tokens")),
        sa.UniqueConstraint(
            "token_hash", name=op.f("uq_student_verification_tokens_token_hash")
        ),
    )
    op.create_index(
        "ix_student_verification_tokens_teacher_id",
        "student_verification_tokens",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        "ix_student_verification_tokens_expires_at",
        "student_verification_tokens",
        ["expires_at"],
        unique=False,
    )

    op.add_column("ratings", sa.Column("knowledge_of_material", sa.Integer(), nullable=True))
    op.add_column("ratings", sa.Column("presentation", sa.Integer(), nullable=True))
    op.add_column("ratings", sa.Column("friendliness", sa.Integer(), nullable=True))
    op.add_column("ratings", sa.Column("other", sa.Integer(), nullable=True))
    op.add_column(
        "ratings",
        sa.Column("verification_token_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_ratings_verification_token_id_student_verification_tokens"),
        "ratings",
        "student_verification_tokens",
        ["verification_token_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "knowledge_range",
        "ratings",
        "knowledge_of_material IS NULL OR (knowledge_of_material >= 1 AND knowledge_of_material <= 5)",
    )
    op.create_check_constraint(
        "presentation_range",
        "ratings",
        "presentation IS NULL OR (presentation >= 1 AND presentation <= 5)",
    )
    op.create_check_constraint(
        "friendliness_range",
        "ratings",
        "friendliness IS NULL OR (friendliness >= 1 AND friendliness <= 5)",
    )
    op.create_check_constraint(
        "other_range",
        "ratings",
        "other IS NULL OR (other >= 1 AND other <= 5)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ratings_other_range", "ratings", type_="check")
    op.drop_constraint("ck_ratings_friendliness_range", "ratings", type_="check")
    op.drop_constraint("ck_ratings_presentation_range", "ratings", type_="check")
    op.drop_constraint("ck_ratings_knowledge_range", "ratings", type_="check")
    op.drop_constraint(
        op.f("fk_ratings_verification_token_id_student_verification_tokens"),
        "ratings",
        type_="foreignkey",
    )
    op.drop_column("ratings", "verification_token_id")
    op.drop_column("ratings", "other")
    op.drop_column("ratings", "friendliness")
    op.drop_column("ratings", "presentation")
    op.drop_column("ratings", "knowledge_of_material")

    op.drop_index(
        "ix_student_verification_tokens_expires_at",
        table_name="student_verification_tokens",
    )
    op.drop_index(
        "ix_student_verification_tokens_teacher_id",
        table_name="student_verification_tokens",
    )
    op.drop_table("student_verification_tokens")
