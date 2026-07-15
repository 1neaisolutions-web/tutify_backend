"""Add scope_topic_ids to teacher assignments, worksheets, and exams.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table in ("teacher_assignments", "teacher_worksheets", "teacher_exams"):
        if not _column_exists(table, "scope_topic_ids"):
            op.add_column(
                table,
                sa.Column("scope_topic_ids", postgresql.JSONB(), nullable=True),
            )


def downgrade() -> None:
    for table in ("teacher_exams", "teacher_worksheets", "teacher_assignments"):
        if _column_exists(table, "scope_topic_ids"):
            op.drop_column(table, "scope_topic_ids")
