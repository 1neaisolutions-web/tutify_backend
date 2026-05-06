"""create_teacher_assignment_tables (merge heads)

Revision ID: u6v7w8x9y0z1
Revises: e5f6a7b8c9d0, t5u6v7w8x9y0
Create Date: 2026-05-04
"""

from typing import Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "u6v7w8x9y0z1"
down_revision: Union[str, Tuple[str, str], None] = ("e5f6a7b8c9d0", "t5u6v7w8x9y0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teacher_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("grade", sa.String(length=80), nullable=False),
        sa.Column(
            "assignment_type",
            sa.String(length=80),
            nullable=False,
            server_default="Structured response",
        ),
        sa.Column(
            "rigor_profile",
            sa.String(length=80),
            nullable=False,
            server_default="Standard",
        ),
        sa.Column("student_instructions", sa.Text(), nullable=True),
        sa.Column("teacher_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_pack_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "scope_topics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("scope_refinement", sa.Text(), nullable=True),
        sa.Column("topic_summary", sa.Text(), nullable=True),
        sa.Column(
            "generate_without_sources",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column(
            "brief_topics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("handout_layout", postgresql.JSONB(), nullable=True),
        sa.Column(
            "class_keys",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("topics_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lines_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assigned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("graded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_teacher_assignments_id", "teacher_assignments", ["id"])
    op.create_index("ix_teacher_assignments_tenant_id", "teacher_assignments", ["tenant_id"])
    op.create_index("ix_teacher_assignments_owner_user_id", "teacher_assignments", ["owner_user_id"])
    op.create_index("ix_teacher_assignments_status", "teacher_assignments", ["status"])
    op.create_index(
        "ix_teacher_assignments_tenant_status_updated",
        "teacher_assignments",
        ["tenant_id", "status", "updated_at"],
    )

    op.create_table(
        "teacher_assignment_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_type", sa.String(length=16), nullable=False, server_default="full"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("retrieval_warnings", postgresql.JSONB(), nullable=True),
        sa.Column("retrieval_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["teacher_assignments.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_teacher_assignment_gen_runs_id",
        "teacher_assignment_generation_runs",
        ["id"],
    )
    op.create_index(
        "ix_teacher_assignment_gen_runs_assignment_id",
        "teacher_assignment_generation_runs",
        ["assignment_id"],
    )
    op.create_index(
        "ix_teacher_assignment_gen_runs_idempotency_key",
        "teacher_assignment_generation_runs",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_teacher_assignment_gen_assign_created",
        "teacher_assignment_generation_runs",
        ["assignment_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_teacher_assignment_gen_assign_created",
        table_name="teacher_assignment_generation_runs",
    )
    op.drop_index(
        "ix_teacher_assignment_gen_runs_idempotency_key",
        table_name="teacher_assignment_generation_runs",
    )
    op.drop_index(
        "ix_teacher_assignment_gen_runs_assignment_id",
        table_name="teacher_assignment_generation_runs",
    )
    op.drop_index(
        "ix_teacher_assignment_gen_runs_id",
        table_name="teacher_assignment_generation_runs",
    )
    op.drop_table("teacher_assignment_generation_runs")

    op.drop_index(
        "ix_teacher_assignments_tenant_status_updated",
        table_name="teacher_assignments",
    )
    op.drop_index("ix_teacher_assignments_status", table_name="teacher_assignments")
    op.drop_index("ix_teacher_assignments_owner_user_id", table_name="teacher_assignments")
    op.drop_index("ix_teacher_assignments_tenant_id", table_name="teacher_assignments")
    op.drop_index("ix_teacher_assignments_id", table_name="teacher_assignments")
    op.drop_table("teacher_assignments")
