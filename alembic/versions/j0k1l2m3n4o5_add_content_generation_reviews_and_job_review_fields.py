"""add_content_generation_reviews_and_job_review_fields

Revision ID: j0k1l2m3n4o5
Revises: h9i0j1k2l3m4
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "h9i0j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # content_generation_reviews table
    op.create_table(
        "content_generation_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("review_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_id"], ["content_generation_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        op.f("ix_content_generation_reviews_id"),
        "content_generation_reviews",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_reviews_job_id"),
        "content_generation_reviews",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_reviews_reviewer_user_id"),
        "content_generation_reviews",
        ["reviewer_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_reviews_decision"),
        "content_generation_reviews",
        ["decision"],
        unique=False,
    )

    # Add review-related fields to content_generation_jobs
    op.add_column(
        "content_generation_jobs",
        sa.Column("review_required", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "content_generation_jobs",
        sa.Column("publication_policy_decision", sa.String(50), nullable=True),
    )
    op.add_column(
        "content_generation_jobs",
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "content_generation_jobs",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_generation_jobs",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_content_generation_jobs_approved_by_user_id"),
        "content_generation_jobs",
        ["approved_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_content_generation_jobs_approved_by_user_id_users",
        "content_generation_jobs",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_content_generation_jobs_approved_by_user_id_users",
        "content_generation_jobs",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_content_generation_jobs_approved_by_user_id"),
        table_name="content_generation_jobs",
    )
    op.drop_column("content_generation_jobs", "rejection_reason")
    op.drop_column("content_generation_jobs", "approved_at")
    op.drop_column("content_generation_jobs", "approved_by_user_id")
    op.drop_column("content_generation_jobs", "publication_policy_decision")
    op.drop_column("content_generation_jobs", "review_required")

    op.drop_index(
        op.f("ix_content_generation_reviews_decision"),
        table_name="content_generation_reviews",
    )
    op.drop_index(
        op.f("ix_content_generation_reviews_reviewer_user_id"),
        table_name="content_generation_reviews",
    )
    op.drop_index(
        op.f("ix_content_generation_reviews_job_id"),
        table_name="content_generation_reviews",
    )
    op.drop_index(
        op.f("ix_content_generation_reviews_id"),
        table_name="content_generation_reviews",
    )
    op.drop_table("content_generation_reviews")

