"""merge_personalization_heads

Merges the two parallel heads before personalization migrations.

Revision ID: n1o2p3q4r5s6
Revises: b1c2d3e4f5a6, m3n4o5p6q7r8
Create Date: 2026-03-31

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, tuple, None] = ("b1c2d3e4f5a6", "m3n4o5p6q7r8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
