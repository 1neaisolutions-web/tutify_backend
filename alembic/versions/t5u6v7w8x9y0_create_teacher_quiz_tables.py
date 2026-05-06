"""create_teacher_quiz_tables

Revision ID: t5u6v7w8x9y0
Revises: r4s5t6u7v8w9
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision: str = "t5u6v7w8x9y0"
down_revision: Union[str, None] = "r4s5t6u7v8w9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Some dev databases were created before Alembic tracked this revision.
    # If the tables already exist, treat this migration as a no-op so later
    # revisions (e.g. teacher assignments) can still be applied.
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "teacher_quizzes" in existing:
        return

    op.create_table(
        "teacher_quizzes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("grade", sa.String(length=80), nullable=False),
        sa.Column("student_instructions", sa.Text(), nullable=True),
        sa.Column("teacher_notes", sa.Text(), nullable=True),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_pack_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scope_topics", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scope_refinement", sa.Text(), nullable=True),
        sa.Column("topic_summary", sa.Text(), nullable=True),
        sa.Column("generate_without_sources", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("shuffle_answers", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("negative_marking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("handout_layout", postgresql.JSONB(), nullable=True),
        sa.Column("class_keys", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("questions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_marks", sa.Float(), nullable=False, server_default="0"),
        sa.Column("submission_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_score", sa.Float(), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_teacher_quizzes_id", "teacher_quizzes", ["id"])
    op.create_index("ix_teacher_quizzes_tenant_id", "teacher_quizzes", ["tenant_id"])
    op.create_index("ix_teacher_quizzes_owner_user_id", "teacher_quizzes", ["owner_user_id"])
    op.create_index("ix_teacher_quizzes_status", "teacher_quizzes", ["status"])
    op.create_index(
        "ix_teacher_quizzes_tenant_status_updated",
        "teacher_quizzes",
        ["tenant_id", "status", "updated_at"],
    )

    op.create_table(
        "teacher_quiz_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("points", sa.Float(), nullable=False, server_default="1"),
        sa.Column("options", postgresql.JSONB(), nullable=True),
        sa.Column("response_lines", sa.Integer(), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["quiz_id"], ["teacher_quizzes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teacher_quiz_questions_id", "teacher_quiz_questions", ["id"])
    op.create_index("ix_teacher_quiz_questions_quiz_id", "teacher_quiz_questions", ["quiz_id"])

    op.create_table(
        "teacher_quiz_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("retrieval_warnings", postgresql.JSONB(), nullable=True),
        sa.Column("retrieval_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["quiz_id"], ["teacher_quizzes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teacher_quiz_generation_runs_id", "teacher_quiz_generation_runs", ["id"])
    op.create_index("ix_teacher_quiz_generation_runs_quiz_id", "teacher_quiz_generation_runs", ["quiz_id"])
    op.create_index(
        "ix_teacher_quiz_generation_runs_idempotency_key",
        "teacher_quiz_generation_runs",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_teacher_quiz_gen_quiz_created",
        "teacher_quiz_generation_runs",
        ["quiz_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_quiz_gen_quiz_created", table_name="teacher_quiz_generation_runs")
    op.drop_index("ix_teacher_quiz_generation_runs_idempotency_key", table_name="teacher_quiz_generation_runs")
    op.drop_index("ix_teacher_quiz_generation_runs_quiz_id", table_name="teacher_quiz_generation_runs")
    op.drop_index("ix_teacher_quiz_generation_runs_id", table_name="teacher_quiz_generation_runs")
    op.drop_table("teacher_quiz_generation_runs")

    op.drop_index("ix_teacher_quiz_questions_quiz_id", table_name="teacher_quiz_questions")
    op.drop_index("ix_teacher_quiz_questions_id", table_name="teacher_quiz_questions")
    op.drop_table("teacher_quiz_questions")

    op.drop_index("ix_teacher_quizzes_tenant_status_updated", table_name="teacher_quizzes")
    op.drop_index("ix_teacher_quizzes_status", table_name="teacher_quizzes")
    op.drop_index("ix_teacher_quizzes_owner_user_id", table_name="teacher_quizzes")
    op.drop_index("ix_teacher_quizzes_tenant_id", table_name="teacher_quizzes")
    op.drop_index("ix_teacher_quizzes_id", table_name="teacher_quizzes")
    op.drop_table("teacher_quizzes")

