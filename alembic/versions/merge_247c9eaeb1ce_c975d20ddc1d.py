"""Merge 247c9eaeb1ce and c975d20ddc1d (revision present in DB)

Revision ID: merge_247c9eaeb1ce_c975d20ddc1d
Revises: 247c9eaeb1ce, c975d20ddc1d
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op

revision: str = "merge_247c9eaeb1ce_c975d20ddc1d"
down_revision: Union[str, None] = ("247c9eaeb1ce", "c975d20ddc1d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
