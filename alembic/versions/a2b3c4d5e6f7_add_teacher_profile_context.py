"""add_teacher_profile_context

Revision ID: a2b3c4d5e6f7
Revises: f7g8h9i0j1k2
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f7g8h9i0j1k2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teacher_profile_context",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("region", sa.String(150), nullable=False),
        sa.Column("school_type", sa.String(50), nullable=False),
        sa.Column("grade_band", sa.String(50), nullable=False),
        sa.Column("subjects", sa.JSON(), nullable=False),
        sa.Column("language_preference", sa.String(100), nullable=False),
        sa.Column("school_name", sa.String(200), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("curriculum_framework", sa.String(80), nullable=True),
        sa.Column("years_experience", sa.String(20), nullable=True),
        sa.Column("professional_goals", sa.JSON(), nullable=True),
        sa.Column("context_resolution_status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_teacher_profile_context_user_id"), "teacher_profile_context", ["user_id"], unique=True)
    op.create_index(op.f("ix_teacher_profile_context_country"), "teacher_profile_context", ["country"], unique=False)
    op.create_index(op.f("ix_teacher_profile_context_region"), "teacher_profile_context", ["region"], unique=False)
    op.create_index(
        op.f("ix_teacher_profile_context_context_resolution_status"),
        "teacher_profile_context",
        ["context_resolution_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_teacher_profile_context_context_resolution_status"), table_name="teacher_profile_context")
    op.drop_index(op.f("ix_teacher_profile_context_region"), table_name="teacher_profile_context")
    op.drop_index(op.f("ix_teacher_profile_context_country"), table_name="teacher_profile_context")
    op.drop_index(op.f("ix_teacher_profile_context_user_id"), table_name="teacher_profile_context")
    op.drop_table("teacher_profile_context")
