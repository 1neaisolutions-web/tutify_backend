"""add user preferences

Revision ID: 4d20b4d74ac7
Revises: z2a3b4c5d6e7
Create Date: 2026-05-05 14:56:54.320170

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4d20b4d74ac7'
down_revision: Union[str, None] = 'z2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Some environments enforce aggressive statement timeouts.
    # Adding a nullable JSON column can be delayed by locks; disable timeout for this transaction.
    op.execute("SET LOCAL statement_timeout = 0")
    op.add_column('users', sa.Column('preferences', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'preferences')

