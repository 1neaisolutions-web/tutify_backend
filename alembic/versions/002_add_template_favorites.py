"""Add template favorites table

Revision ID: 002_add_template_favorites
Revises: 001_create_template_models
Create Date: 2024-01-XX XX:XX:XX.XXXXXX
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_template_favorites'
down_revision: Union[str, None] = '001_create_template_models'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create template_favorites table
    op.create_table(
        'template_favorites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='CASCADE'),
    )
    
    # Create indexes
    op.create_index(op.f('ix_template_favorites_id'), 'template_favorites', ['id'], unique=False)
    op.create_index(op.f('ix_template_favorites_template_id'), 'template_favorites', ['template_id'], unique=False)
    op.create_index(op.f('ix_template_favorites_user_id'), 'template_favorites', ['user_id'], unique=False)
    op.create_index(op.f('ix_template_favorites_session_id'), 'template_favorites', ['session_id'], unique=False)
    
    # Create unique constraints
    # Note: PostgreSQL allows NULL in unique constraints, so we need to handle this carefully
    # We'll create partial unique indexes that ignore NULLs
    op.execute("""
        CREATE UNIQUE INDEX uq_template_favorite_user 
        ON template_favorites (template_id, user_id) 
        WHERE user_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_template_favorite_session 
        ON template_favorites (template_id, session_id) 
        WHERE session_id IS NOT NULL
    """)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('uq_template_favorite_session', table_name='template_favorites')
    op.drop_index('uq_template_favorite_user', table_name='template_favorites')
    op.drop_index(op.f('ix_template_favorites_session_id'), table_name='template_favorites')
    op.drop_index(op.f('ix_template_favorites_user_id'), table_name='template_favorites')
    op.drop_index(op.f('ix_template_favorites_template_id'), table_name='template_favorites')
    op.drop_index(op.f('ix_template_favorites_id'), table_name='template_favorites')
    
    # Drop table
    op.drop_table('template_favorites')

