"""create_content_generation_jobs_table

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "h9i0j1k2l3m4"
down_revision: Union[str, None] = "g8h9i0j1k2l3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("generation_strategy", sa.String(50), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(100), nullable=True),
        sa.Column("grade_band", sa.String(50), nullable=True),
        sa.Column("difficulty", sa.String(50), nullable=True),
        sa.Column("locale", sa.String(20), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("current_step", sa.String(50), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("result_content_id", sa.String(150), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("step_outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_content_generation_jobs_id"), "content_generation_jobs", ["id"], unique=False)
    op.create_index(
        op.f("ix_content_generation_jobs_requested_by_user_id"),
        "content_generation_jobs",
        ["requested_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_jobs_content_type"),
        "content_generation_jobs",
        ["content_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_jobs_status"),
        "content_generation_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_jobs_created_at"),
        "content_generation_jobs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_generation_jobs_created_at"), table_name="content_generation_jobs")
    op.drop_index(op.f("ix_content_generation_jobs_status"), table_name="content_generation_jobs")
    op.drop_index(op.f("ix_content_generation_jobs_content_type"), table_name="content_generation_jobs")
    op.drop_index(op.f("ix_content_generation_jobs_requested_by_user_id"), table_name="content_generation_jobs")
    op.drop_index(op.f("ix_content_generation_jobs_id"), table_name="content_generation_jobs")
    op.drop_table("content_generation_jobs")
