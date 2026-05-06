"""add_teacher_worksheet_tables

Revision ID: w8x9y0z1a2b4
Revises: u6v7w8x9y0z1
Create Date: 2026-05-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision: str = "w8x9y0z1a2b4"
down_revision: Union[str, None] = "u6v7w8x9y0z1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if "teacher_worksheets" in existing:
        return

    op.create_table(
        "teacher_worksheets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("grade", sa.String(length=80), nullable=False),
        sa.Column("output_format", sa.String(length=32), nullable=False, server_default="interactive_digital"),
        sa.Column("class_keys", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("student_instructions", sa.Text(), nullable=True),
        sa.Column("teacher_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_pack_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scope_topics", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scope_refinement", sa.Text(), nullable=True),
        sa.Column("topic_summary", sa.Text(), nullable=True),
        sa.Column("generate_without_sources", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("handout_layout", postgresql.JSONB(), nullable=True),
        sa.Column("sessions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submission_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_score", sa.Float(), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_teacher_worksheets_id", "teacher_worksheets", ["id"])
    op.create_index("ix_teacher_worksheets_tenant_id", "teacher_worksheets", ["tenant_id"])
    op.create_index("ix_teacher_worksheets_owner_user_id", "teacher_worksheets", ["owner_user_id"])
    op.create_index("ix_teacher_worksheets_status", "teacher_worksheets", ["status"])
    op.create_index(
        "ix_teacher_worksheets_tenant_status_updated",
        "teacher_worksheets",
        ["tenant_id", "status", "updated_at"],
    )

    op.create_table(
        "teacher_worksheet_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("worksheet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Session 1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["worksheet_id"], ["teacher_worksheets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teacher_worksheet_sessions_worksheet", "teacher_worksheet_sessions", ["worksheet_id", "sort_order"])

    op.create_table(
        "teacher_worksheet_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("worksheet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("points", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["worksheet_id"], ["teacher_worksheets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["teacher_worksheet_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_teacher_worksheet_blocks_session", "teacher_worksheet_blocks", ["session_id", "sort_order"])
    op.create_index("ix_teacher_worksheet_blocks_worksheet", "teacher_worksheet_blocks", ["worksheet_id"])

    op.create_table(
        "teacher_worksheet_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("worksheet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("target_block_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("retrieval_warnings", postgresql.JSONB(), nullable=True),
        sa.Column("retrieval_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["worksheet_id"], ["teacher_worksheets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wsheet_gen_worksheet_created", "teacher_worksheet_generation_runs", ["worksheet_id", "created_at"])
    op.create_index("ix_wsheet_gen_idempotency_key", "teacher_worksheet_generation_runs", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_wsheet_gen_idempotency_key", table_name="teacher_worksheet_generation_runs")
    op.drop_index("ix_wsheet_gen_worksheet_created", table_name="teacher_worksheet_generation_runs")
    op.drop_table("teacher_worksheet_generation_runs")

    op.drop_index("ix_teacher_worksheet_blocks_worksheet", table_name="teacher_worksheet_blocks")
    op.drop_index("ix_teacher_worksheet_blocks_session", table_name="teacher_worksheet_blocks")
    op.drop_table("teacher_worksheet_blocks")

    op.drop_index("ix_teacher_worksheet_sessions_worksheet", table_name="teacher_worksheet_sessions")
    op.drop_table("teacher_worksheet_sessions")

    op.drop_index("ix_teacher_worksheets_tenant_status_updated", table_name="teacher_worksheets")
    op.drop_index("ix_teacher_worksheets_status", table_name="teacher_worksheets")
    op.drop_index("ix_teacher_worksheets_owner_user_id", table_name="teacher_worksheets")
    op.drop_index("ix_teacher_worksheets_tenant_id", table_name="teacher_worksheets")
    op.drop_index("ix_teacher_worksheets_id", table_name="teacher_worksheets")
    op.drop_table("teacher_worksheets")
