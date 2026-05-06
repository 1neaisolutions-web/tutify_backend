"""exam_idempotency_scoped_to_exam

Revision ID: d1e2f3a4b5c6
Revises: c8d9e0f1a2b3
Create Date: 2026-05-06

Scope teacher_exam_generation_runs idempotency to exam_id.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Old: unique on (idempotency_key) globally
    op.drop_index("ix_exam_gen_idempotency", table_name="teacher_exam_generation_runs", if_exists=True)

    # New: unique on (exam_id, idempotency_key) — avoids collisions across different exams.
    op.create_index(
        "ix_exam_gen_idempotency",
        "teacher_exam_generation_runs",
        ["exam_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_exam_gen_idempotency", table_name="teacher_exam_generation_runs", if_exists=True)
    op.create_index(
        "ix_exam_gen_idempotency",
        "teacher_exam_generation_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

