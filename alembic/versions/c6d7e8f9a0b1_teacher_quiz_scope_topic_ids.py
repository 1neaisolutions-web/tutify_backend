"""Add scope_topic_ids and scope_book_ids to teacher_quizzes.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _column_exists("teacher_quizzes", "scope_topic_ids"):
        op.add_column(
            "teacher_quizzes",
            sa.Column("scope_topic_ids", postgresql.JSONB(), nullable=True),
        )
    if not _column_exists("teacher_quizzes", "scope_book_ids"):
        op.add_column(
            "teacher_quizzes",
            sa.Column("scope_book_ids", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("teacher_quizzes", "scope_book_ids")
    op.drop_column("teacher_quizzes", "scope_topic_ids")
