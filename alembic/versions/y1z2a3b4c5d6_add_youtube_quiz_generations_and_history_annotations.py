"""add youtube quiz generations and history annotations

Revision ID: y1z2a3b4c5d6
Revises: x9y0z1a2b3c4
Create Date: 2026-05-05 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "y1z2a3b4c5d6"
down_revision: Union[str, None] = "x9y0z1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "youtube_quiz_generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_url", sa.Text(), nullable=False),
        sa.Column("grade_band", sa.String(length=80), nullable=False),
        sa.Column("subject_lens", sa.String(length=120), nullable=False),
        sa.Column("learning_focus", sa.String(length=120), nullable=False),
        sa.Column("quiz_language", sa.String(length=40), nullable=False),
        sa.Column("question_styles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("lesson_strategy_id", sa.String(length=64), nullable=True),
        sa.Column("difficulty_level", sa.String(length=32), nullable=True),
        sa.Column("accessibility_mode", sa.Boolean(), nullable=False),
        sa.Column("video_id", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_youtube_quiz_generations_id"), "youtube_quiz_generations", ["id"], unique=False)
    op.create_index(op.f("ix_youtube_quiz_generations_user_id"), "youtube_quiz_generations", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_youtube_quiz_generations_created_at"),
        "youtube_quiz_generations",
        ["created_at"],
        unique=False,
    )
    op.create_index("idx_youtube_quiz_user_created_at", "youtube_quiz_generations", ["user_id", "created_at"], unique=False)

    op.create_table(
        "user_content_pins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_user_content_pin"),
    )
    op.create_index(op.f("ix_user_content_pins_user_id"), "user_content_pins", ["user_id"], unique=False)

    op.create_table(
        "user_content_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hint", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_user_content_feedback"),
    )
    op.create_index(op.f("ix_user_content_feedback_user_id"), "user_content_feedback", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_content_feedback_user_id"), table_name="user_content_feedback")
    op.drop_table("user_content_feedback")

    op.drop_index(op.f("ix_user_content_pins_user_id"), table_name="user_content_pins")
    op.drop_table("user_content_pins")

    op.drop_index("idx_youtube_quiz_user_created_at", table_name="youtube_quiz_generations")
    op.drop_index(op.f("ix_youtube_quiz_generations_created_at"), table_name="youtube_quiz_generations")
    op.drop_index(op.f("ix_youtube_quiz_generations_user_id"), table_name="youtube_quiz_generations")
    op.drop_index(op.f("ix_youtube_quiz_generations_id"), table_name="youtube_quiz_generations")
    op.drop_table("youtube_quiz_generations")

