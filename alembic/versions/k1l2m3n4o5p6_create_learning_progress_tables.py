"""create_learning_progress_tables

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # learning_sessions
    op.create_table(
        "learning_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("session_status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locale", sa.String(20), nullable=True),
        sa.Column(
            "session_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_learning_sessions_id"), "learning_sessions", ["id"], unique=False)
    op.create_index(
        op.f("ix_learning_sessions_teacher_id"),
        "learning_sessions",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_sessions_content_id"),
        "learning_sessions",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_sessions_content_type"),
        "learning_sessions",
        ["content_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_sessions_session_status"),
        "learning_sessions",
        ["session_status"],
        unique=False,
    )
    op.create_index(
        "idx_learning_sessions_teacher_content_status",
        "learning_sessions",
        ["teacher_id", "content_id", "session_status"],
        unique=False,
    )

    # learning_events
    op.create_table(
        "learning_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_learning_events_id"), "learning_events", ["id"], unique=False)
    op.create_index(
        op.f("ix_learning_events_session_id"),
        "learning_events",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_events_teacher_id"),
        "learning_events",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_events_content_id"),
        "learning_events",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_events_event_type"),
        "learning_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_learning_events_created_at"),
        "learning_events",
        ["created_at"],
        unique=False,
    )

    # recommendation_events
    op.create_table(
        "recommendation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=True),
        sa.Column("recommendation_source", sa.String(100), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        op.f("ix_recommendation_events_id"),
        "recommendation_events",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_events_teacher_id"),
        "recommendation_events",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_events_content_id"),
        "recommendation_events",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_events_event_type"),
        "recommendation_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_events_recommendation_source"),
        "recommendation_events",
        ["recommendation_source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_events_created_at"),
        "recommendation_events",
        ["created_at"],
        unique=False,
    )

    # content_feedback
    op.create_table(
        "content_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("difficulty_feedback", sa.String(50), nullable=True),
        sa.Column("usefulness_feedback", sa.String(50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "feedback_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_content_feedback_id"), "content_feedback", ["id"], unique=False)
    op.create_index(
        op.f("ix_content_feedback_teacher_id"),
        "content_feedback",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_feedback_content_id"),
        "content_feedback",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_feedback_created_at"),
        "content_feedback",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_feedback_created_at"), table_name="content_feedback")
    op.drop_index(op.f("ix_content_feedback_content_id"), table_name="content_feedback")
    op.drop_index(op.f("ix_content_feedback_teacher_id"), table_name="content_feedback")
    op.drop_index(op.f("ix_content_feedback_id"), table_name="content_feedback")
    op.drop_table("content_feedback")

    op.drop_index(
        op.f("ix_recommendation_events_created_at"),
        table_name="recommendation_events",
    )
    op.drop_index(
        op.f("ix_recommendation_events_recommendation_source"),
        table_name="recommendation_events",
    )
    op.drop_index(
        op.f("ix_recommendation_events_event_type"),
        table_name="recommendation_events",
    )
    op.drop_index(
        op.f("ix_recommendation_events_content_id"),
        table_name="recommendation_events",
    )
    op.drop_index(
        op.f("ix_recommendation_events_teacher_id"),
        table_name="recommendation_events",
    )
    op.drop_index(op.f("ix_recommendation_events_id"), table_name="recommendation_events")
    op.drop_table("recommendation_events")

    op.drop_index(
        op.f("ix_learning_events_created_at"),
        table_name="learning_events",
    )
    op.drop_index(
        op.f("ix_learning_events_event_type"),
        table_name="learning_events",
    )
    op.drop_index(
        op.f("ix_learning_events_content_id"),
        table_name="learning_events",
    )
    op.drop_index(
        op.f("ix_learning_events_teacher_id"),
        table_name="learning_events",
    )
    op.drop_index(
        op.f("ix_learning_events_session_id"),
        table_name="learning_events",
    )
    op.drop_index(op.f("ix_learning_events_id"), table_name="learning_events")
    op.drop_table("learning_events")

    op.drop_index(
        "idx_learning_sessions_teacher_content_status",
        table_name="learning_sessions",
    )
    op.drop_index(
        op.f("ix_learning_sessions_session_status"),
        table_name="learning_sessions",
    )
    op.drop_index(
        op.f("ix_learning_sessions_content_type"),
        table_name="learning_sessions",
    )
    op.drop_index(
        op.f("ix_learning_sessions_content_id"),
        table_name="learning_sessions",
    )
    op.drop_index(
        op.f("ix_learning_sessions_teacher_id"),
        table_name="learning_sessions",
    )
    op.drop_index(op.f("ix_learning_sessions_id"), table_name="learning_sessions")
    op.drop_table("learning_sessions")

