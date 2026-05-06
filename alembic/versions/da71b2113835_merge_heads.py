"""merge_heads

Revision ID: da71b2113835
Revises: a1b2c3d4e5f6, c975d20ddc1d
Create Date: 2026-01-25 13:58:12.251258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da71b2113835'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'c975d20ddc1d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

