"""merge pixgen head with existing head

Revision ID: 12a18f870c9f
Revises: 005_merge_heads, f1a2b3c4d5e6
Create Date: 2026-04-14 22:44:46.707563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12a18f870c9f'
down_revision: Union[str, None] = ('005_merge_heads', 'f1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

