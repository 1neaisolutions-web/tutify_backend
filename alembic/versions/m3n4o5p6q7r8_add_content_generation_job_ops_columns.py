"""add_content_generation_job_ops_columns

Aligns DB with SQLAlchemy model: job_type, target_subject, priority, source.
Without these columns, ORM SELECTs fail with "column does not exist".

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-03-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_generation_jobs",
        sa.Column("job_type", sa.String(50), nullable=False, server_default="micro_course"),
    )
    op.add_column(
        "content_generation_jobs",
        sa.Column("target_subject", sa.String(100), nullable=True),
    )
    op.add_column(
        "content_generation_jobs",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "content_generation_jobs",
        sa.Column("source", sa.String(50), nullable=True),
    )
    op.create_index(
        op.f("ix_content_generation_jobs_job_type"),
        "content_generation_jobs",
        ["job_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_jobs_target_subject"),
        "content_generation_jobs",
        ["target_subject"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_jobs_source"),
        "content_generation_jobs",
        ["source"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_generation_jobs_source"), table_name="content_generation_jobs")
    op.drop_index(
        op.f("ix_content_generation_jobs_target_subject"), table_name="content_generation_jobs"
    )
    op.drop_index(op.f("ix_content_generation_jobs_job_type"), table_name="content_generation_jobs")
    op.drop_column("content_generation_jobs", "source")
    op.drop_column("content_generation_jobs", "priority")
    op.drop_column("content_generation_jobs", "target_subject")
    op.drop_column("content_generation_jobs", "job_type")
