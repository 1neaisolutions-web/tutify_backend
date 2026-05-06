"""add_profile_picture_url_to_users

Revision ID: c975d20ddc1d
Revises: cb7fc7887327
Create Date: 2026-01-09 02:25:48.675286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c975d20ddc1d'
down_revision: Union[str, None] = 'cb7fc7887327'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add profile_picture_url column to users table only if it doesn't exist
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    if 'profile_picture_url' not in existing_columns:
        op.add_column('users', 
            sa.Column('profile_picture_url', sa.String(length=500), nullable=True)
        )


def downgrade() -> None:
    # Remove profile_picture_url column from users table
    op.drop_column('users', 'profile_picture_url')

