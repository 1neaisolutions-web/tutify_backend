"""add_teacher_exam_domain

Revision ID: x9y0z1a2b3c4
Revises: w8x9y0z1a2b4
Create Date: 2026-05-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "x9y0z1a2b3c4"
down_revision: Union[str, None] = "w8x9y0z1a2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "teacher_exams" in existing:
        return

    op.create_table(
        "teacher_exams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("grade", sa.String(length=80), nullable=False),
        sa.Column("exam_type", sa.String(length=80), nullable=False, server_default="Unit test"),
        sa.Column("term", sa.String(length=40), nullable=False, server_default="Term 1"),
        sa.Column("international_standard", sa.String(length=80), nullable=False, server_default="Standard"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("total_marks", sa.Float(), nullable=False, server_default="0"),
        sa.Column("schedule_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("class_keys", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("completion_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("section_target_count", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("source_pack_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scope_topics", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scope_refinement", sa.Text(), nullable=True),
        sa.Column("topic_summary", sa.Text(), nullable=True),
        sa.Column("generate_without_sources", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("paper_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("handout_layout", postgresql.JSONB(), nullable=True),
        sa.Column("student_instructions", sa.Text(), nullable=True),
        sa.Column("teacher_notes", sa.Text(), nullable=True),
        sa.Column("sections_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mcq_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("short_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("long_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submission_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_score", sa.Float(), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_teacher_exams_id", "teacher_exams", ["id"])
    op.create_index("ix_teacher_exams_tenant_id", "teacher_exams", ["tenant_id"])
    op.create_index("ix_teacher_exams_owner_user_id", "teacher_exams", ["owner_user_id"])
    op.create_index("ix_teacher_exams_status", "teacher_exams", ["status"])
    op.create_index(
        "ix_teacher_exams_tenant_status_updated",
        "teacher_exams",
        ["tenant_id", "status", "updated_at"],
    )
    op.create_index("ix_teacher_exams_tenant_schedule", "teacher_exams", ["tenant_id", "schedule_start"])

    op.create_table(
        "teacher_exam_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("marks", sa.Float(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["teacher_exams.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teacher_exam_sections_id", "teacher_exam_sections", ["id"])
    op.create_index("ix_teacher_exam_sections_exam_id", "teacher_exam_sections", ["exam_id"])
    op.create_index("ix_teacher_exam_sections_exam", "teacher_exam_sections", ["exam_id", "sort_order"])

    op.create_table(
        "teacher_exam_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_type", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=True),
        sa.Column("subparts", postgresql.JSONB(), nullable=True),
        sa.Column("marks_per", sa.Float(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["exam_id"], ["teacher_exams.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teacher_exam_questions_id", "teacher_exam_questions", ["id"])
    op.create_index("ix_teacher_exam_questions_exam_id", "teacher_exam_questions", ["exam_id"])
    op.create_index(
        "ix_teacher_exam_questions_exam_type",
        "teacher_exam_questions",
        ["exam_id", "question_type", "sort_order"],
    )

    op.create_table(
        "teacher_exam_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("target_question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("retrieval_warnings", postgresql.JSONB(), nullable=True),
        sa.Column("retrieval_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["teacher_exams.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teacher_exam_generation_runs_id", "teacher_exam_generation_runs", ["id"])
    op.create_index("ix_teacher_exam_generation_runs_exam_id", "teacher_exam_generation_runs", ["exam_id"])
    op.create_index(
        "ix_exam_gen_exam_created",
        "teacher_exam_generation_runs",
        ["exam_id", "created_at"],
    )
    op.create_index(
        "ix_exam_gen_idempotency",
        "teacher_exam_generation_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_exam_gen_idempotency", table_name="teacher_exam_generation_runs")
    op.drop_index("ix_exam_gen_exam_created", table_name="teacher_exam_generation_runs")
    op.drop_index("ix_teacher_exam_generation_runs_exam_id", table_name="teacher_exam_generation_runs")
    op.drop_index("ix_teacher_exam_generation_runs_id", table_name="teacher_exam_generation_runs")
    op.drop_table("teacher_exam_generation_runs")

    op.drop_index("ix_teacher_exam_questions_exam_type", table_name="teacher_exam_questions")
    op.drop_index("ix_teacher_exam_questions_exam_id", table_name="teacher_exam_questions")
    op.drop_index("ix_teacher_exam_questions_id", table_name="teacher_exam_questions")
    op.drop_table("teacher_exam_questions")

    op.drop_index("ix_teacher_exam_sections_exam", table_name="teacher_exam_sections")
    op.drop_index("ix_teacher_exam_sections_exam_id", table_name="teacher_exam_sections")
    op.drop_index("ix_teacher_exam_sections_id", table_name="teacher_exam_sections")
    op.drop_table("teacher_exam_sections")

    op.drop_index("ix_teacher_exams_tenant_schedule", table_name="teacher_exams")
    op.drop_index("ix_teacher_exams_tenant_status_updated", table_name="teacher_exams")
    op.drop_index("ix_teacher_exams_status", table_name="teacher_exams")
    op.drop_index("ix_teacher_exams_owner_user_id", table_name="teacher_exams")
    op.drop_index("ix_teacher_exams_tenant_id", table_name="teacher_exams")
    op.drop_index("ix_teacher_exams_id", table_name="teacher_exams")
    op.drop_table("teacher_exams")
