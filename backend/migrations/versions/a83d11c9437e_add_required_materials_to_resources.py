"""add required materials to resources

Revision ID: a83d11c9437e
Revises: d4e5f6a7b8c9
Create Date: 2026-09-20 02:11:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a83d11c9437e"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column(
            "required_materials",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_resources_required_materials",
        "resources",
        ["required_materials"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resources_required_materials",
        table_name="resources",
        postgresql_using="gin",
    )
    op.drop_column("resources", "required_materials")
