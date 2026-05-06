"""Merge multiple heads (004_stub_config_versions + merge_247c9eaeb1ce_c975d20ddc1d)

Revision ID: 005_merge_heads
Revises: 004_stub_config_versions, merge_247c9eaeb1ce_c975d20ddc1d
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op

revision: str = "005_merge_heads"
down_revision: Union[str, None] = ("004_stub_config_versions", "merge_247c9eaeb1ce_c975d20ddc1d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
