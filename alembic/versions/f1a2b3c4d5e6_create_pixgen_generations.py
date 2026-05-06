"""create_pixgen_generations

Revision ID: f1a2b3c4d5e6
Revises: cb7fc7887327
Create Date: 2026-04-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "cb7fc7887327"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pixgen_generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("style_preset", sa.String(length=120), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=50), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pixgen_generations_id"), "pixgen_generations", ["id"], unique=False)
    op.create_index(op.f("ix_pixgen_generations_status"), "pixgen_generations", ["status"], unique=False)
    op.create_index(op.f("ix_pixgen_generations_user_id"), "pixgen_generations", ["user_id"], unique=False)
    op.create_index("idx_pixgen_status_created_at", "pixgen_generations", ["status", "created_at"], unique=False)
    op.create_index("idx_pixgen_user_created_at", "pixgen_generations", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_pixgen_user_created_at", table_name="pixgen_generations")
    op.drop_index("idx_pixgen_status_created_at", table_name="pixgen_generations")
    op.drop_index(op.f("ix_pixgen_generations_user_id"), table_name="pixgen_generations")
    op.drop_index(op.f("ix_pixgen_generations_status"), table_name="pixgen_generations")
    op.drop_index(op.f("ix_pixgen_generations_id"), table_name="pixgen_generations")
    op.drop_table("pixgen_generations")
