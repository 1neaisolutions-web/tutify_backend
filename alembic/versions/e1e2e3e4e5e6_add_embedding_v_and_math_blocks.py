"""add_embedding_v_and_math_blocks

Revision ID: e1e2e3e4e5e6
Revises: da71b2113835
Create Date: 2026-01-28 12:00:00.000000

Additive, backwards-compatible:
- chunks: embedding_v (vector), embedding_dim (int), embedding_provider (text)
- math_blocks table for math-aware extraction
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e1e2e3e4e5e6'
down_revision: Union[str, None] = 'da71b2113835'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chunks: additive columns for dimension-safe embeddings (legacy embedding untouched)
    # embedding_v: flexible-dimension vector; use 1536 max and zero-pad smaller (e.g. 384)
    op.execute("ALTER TABLE chunks ADD COLUMN embedding_v vector(1536);")
    op.add_column('chunks', sa.Column('embedding_dim', sa.Integer(), nullable=True))
    op.add_column('chunks', sa.Column('embedding_provider', sa.String(length=100), nullable=True))

    # math_blocks table for math-aware extraction (optional persistence)
    op.create_table(
        'math_blocks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('page_no', sa.Integer(), nullable=False),
        sa.Column('block_type', sa.String(length=50), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('normalized_text', sa.Text(), nullable=True),
        sa.Column('bbox_json', postgresql.JSONB(), nullable=True),
        sa.Column('confidence', sa.Numeric(5, 2), nullable=True),
        sa.Column('provider_name', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_math_blocks_document_id'), 'math_blocks', ['document_id'], unique=False)
    op.create_index('idx_math_blocks_doc_page', 'math_blocks', ['document_id', 'page_no'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_math_blocks_doc_page', table_name='math_blocks')
    op.drop_index(op.f('ix_math_blocks_document_id'), table_name='math_blocks')
    op.drop_table('math_blocks')

    op.drop_column('chunks', 'embedding_provider')
    op.drop_column('chunks', 'embedding_dim')
    op.execute("ALTER TABLE chunks DROP COLUMN embedding_v;")
