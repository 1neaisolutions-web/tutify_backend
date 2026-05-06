"""add_active_membership_id_to_refresh_tokens

Revision ID: cb7fc7887327
Revises: d6e42d4a8046
Create Date: 2026-01-05 02:15:24.158645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'cb7fc7887327'
down_revision: Union[str, None] = 'd6e42d4a8046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add active_membership_id column to refresh_tokens (skip if already added by 9648346e2f84)
    conn = op.get_bind()
    insp = inspect(conn)
    columns = [c["name"] for c in insp.get_columns("refresh_tokens")]
    if "active_membership_id" not in columns:
        op.add_column("refresh_tokens", sa.Column("active_membership_id", sa.UUID(), nullable=True))
    # Create index only if missing (9648346e2f84 may have already created it)
    index_names = [idx["name"] for idx in insp.get_indexes("refresh_tokens")]
    if "ix_refresh_tokens_active_membership_id" not in index_names:
        op.create_index(op.f("ix_refresh_tokens_active_membership_id"), "refresh_tokens", ["active_membership_id"], unique=False)
    # Create FK only if missing (9648346e2f84 uses fk_refresh_tokens_active_membership)
    existing_fks = [fk["name"] for fk in insp.get_foreign_keys("refresh_tokens")]
    if "fk_refresh_tokens_active_membership_id" not in existing_fks and "fk_refresh_tokens_active_membership" not in existing_fks:
        op.create_foreign_key(
            "fk_refresh_tokens_active_membership_id",
            "refresh_tokens", "user_memberships",
            ["active_membership_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # Remove active_membership_id column from refresh_tokens table
    op.drop_constraint('fk_refresh_tokens_active_membership_id', 'refresh_tokens', type_='foreignkey')
    op.drop_index(op.f('ix_refresh_tokens_active_membership_id'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'active_membership_id')

