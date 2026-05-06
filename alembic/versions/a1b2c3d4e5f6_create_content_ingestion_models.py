"""create_content_ingestion_models

Revision ID: a1b2c3d4e5f6
Revises: 247c9eaeb1ce
Create Date: 2026-01-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '247c9eaeb1ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    
    # Content packs table
    op.create_table(
        'content_packs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('subject', sa.String(length=100), nullable=True),
        sa.Column('grade', sa.String(length=50), nullable=True),
        sa.Column('curriculum', sa.String(length=100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_content_packs_id'), 'content_packs', ['id'], unique=False)
    op.create_index(op.f('ix_content_packs_tenant_id'), 'content_packs', ['tenant_id'], unique=False)
    
    # Documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pack_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='uploaded'),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('remediation_hint', sa.Text(), nullable=True),
        sa.Column('processing_metadata', postgresql.JSONB(), nullable=True),
        sa.Column('chapter_map', postgresql.JSONB(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('author', sa.String(length=200), nullable=True),
        sa.Column('total_pages', sa.Integer(), nullable=True),
        sa.Column('document_hash', sa.String(length=64), nullable=True),
        sa.Column('version_label', sa.String(length=50), nullable=True),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['pack_id'], ['content_packs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_id'), 'documents', ['id'], unique=False)
    op.create_index(op.f('ix_documents_pack_id'), 'documents', ['pack_id'], unique=False)
    op.create_index(op.f('ix_documents_status'), 'documents', ['status'], unique=False)
    op.create_index(op.f('ix_documents_tenant_id'), 'documents', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_documents_document_hash'), 'documents', ['document_hash'], unique=False)
    
    # Page texts table
    op.create_table(
        'page_texts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('page_no', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('char_count', sa.Integer(), nullable=False),
        sa.Column('ocr_confidence', sa.Numeric(5, 2), nullable=True),
        sa.Column('ocr_engine', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_page_texts_id'), 'page_texts', ['id'], unique=False)
    op.create_index(op.f('ix_page_texts_document_id'), 'page_texts', ['document_id'], unique=False)
    op.create_index('idx_page_texts_doc_page', 'page_texts', ['document_id', 'page_no'], unique=False)
    
    # Chunks table (with pgvector embedding)
    # Create table first without embedding column
    op.create_table(
        'chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_id', sa.String(length=100), nullable=False),
        sa.Column('chunk_hash', sa.String(length=64), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('page_start_pdf', sa.Integer(), nullable=True),
        sa.Column('page_end_pdf', sa.Integer(), nullable=True),
        sa.Column('topic_id', sa.String(length=100), nullable=True),
        sa.Column('topic_title', sa.String(length=500), nullable=True),
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'chunk_id', name='uq_chunks_doc_chunk')
    )
    op.create_index(op.f('ix_chunks_id'), 'chunks', ['id'], unique=False)
    op.create_index(op.f('ix_chunks_document_id'), 'chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_chunks_chunk_hash'), 'chunks', ['chunk_hash'], unique=False)
    op.create_index('idx_chunks_doc_topic', 'chunks', ['document_id', 'topic_id'], unique=False)
    op.create_index(op.f('ix_chunks_topic_id'), 'chunks', ['topic_id'], unique=False)
    
    # Add vector column using raw SQL
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1536);")
    
    # Create vector index
    op.execute("""
        CREATE INDEX idx_chunks_embedding ON chunks 
        USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100);
    """)
    
    # Document processing runs table
    op.create_table(
        'document_processing_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('remediation_hint', sa.Text(), nullable=True),
        sa.Column('ocr_mode', sa.String(length=50), nullable=True),
        sa.Column('ocr_engine', sa.String(length=50), nullable=True),
        sa.Column('chunk_size_tokens', sa.Integer(), nullable=True),
        sa.Column('overlap_tokens', sa.Integer(), nullable=True),
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column('index_namespace', sa.String(length=100), nullable=True),
        sa.Column('progress_percentage', sa.Integer(), nullable=True),
        sa.Column('current_step', sa.String(length=100), nullable=True),
        sa.Column('completed_steps', postgresql.JSONB(), nullable=True),
        sa.Column('pages_processed', sa.Integer(), nullable=True),
        sa.Column('chunks_created', sa.Integer(), nullable=True),
        sa.Column('vectors_stored', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_processing_runs_id'), 'document_processing_runs', ['id'], unique=False)
    op.create_index(op.f('ix_document_processing_runs_document_id'), 'document_processing_runs', ['document_id'], unique=False)
    
    # QA validations table
    op.create_table(
        'qa_validations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('qa_status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('thresholds', postgresql.JSONB(), nullable=True),
        sa.Column('golden_query_results', postgresql.JSONB(), nullable=True),
        sa.Column('page_coverage_check', sa.Boolean(), nullable=True),
        sa.Column('text_density_check', sa.Boolean(), nullable=True),
        sa.Column('embedding_completeness_check', sa.Boolean(), nullable=True),
        sa.Column('vector_retrieval_check', sa.Boolean(), nullable=True),
        sa.Column('metrics', postgresql.JSONB(), nullable=True),
        sa.Column('qa_notes', sa.Text(), nullable=True),
        sa.Column('qa_reviewer', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['qa_reviewer'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_qa_validations_id'), 'qa_validations', ['id'], unique=False)
    op.create_index(op.f('ix_qa_validations_document_id'), 'qa_validations', ['document_id'], unique=False)
    
    # Worksheet cache table
    op.create_table(
        'worksheet_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('signature_hash', sa.String(length=64), nullable=False),
        sa.Column('pack_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('topic_id', sa.String(length=100), nullable=True),
        sa.Column('topic_text', sa.String(length=500), nullable=True),
        sa.Column('grade', sa.String(length=50), nullable=True),
        sa.Column('subject', sa.String(length=100), nullable=True),
        sa.Column('difficulty_mix', postgresql.JSONB(), nullable=True),
        sa.Column('num_questions', sa.Integer(), nullable=False),
        sa.Column('format_version', sa.String(length=20), nullable=False, server_default='1.0'),
        sa.Column('worksheet_json', postgresql.JSONB(), nullable=False),
        sa.Column('chunk_ids_used', postgresql.JSONB(), nullable=True),
        sa.Column('retrieval_metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['pack_id'], ['content_packs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('signature_hash')
    )
    op.create_index(op.f('ix_worksheet_cache_id'), 'worksheet_cache', ['id'], unique=False)
    op.create_index(op.f('ix_worksheet_cache_signature_hash'), 'worksheet_cache', ['signature_hash'], unique=True)
    op.create_index(op.f('ix_worksheet_cache_pack_id'), 'worksheet_cache', ['pack_id'], unique=False)
    op.create_index(op.f('ix_worksheet_cache_topic_id'), 'worksheet_cache', ['topic_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_worksheet_cache_topic_id'), table_name='worksheet_cache')
    op.drop_index(op.f('ix_worksheet_cache_pack_id'), table_name='worksheet_cache')
    op.drop_index(op.f('ix_worksheet_cache_signature_hash'), table_name='worksheet_cache')
    op.drop_index(op.f('ix_worksheet_cache_id'), table_name='worksheet_cache')
    op.drop_table('worksheet_cache')
    
    op.drop_index(op.f('ix_qa_validations_document_id'), table_name='qa_validations')
    op.drop_index(op.f('ix_qa_validations_id'), table_name='qa_validations')
    op.drop_table('qa_validations')
    
    op.drop_index(op.f('ix_document_processing_runs_document_id'), table_name='document_processing_runs')
    op.drop_index(op.f('ix_document_processing_runs_id'), table_name='document_processing_runs')
    op.drop_table('document_processing_runs')
    
    op.execute('DROP INDEX IF EXISTS idx_chunks_embedding;')
    op.drop_index(op.f('ix_chunks_topic_id'), table_name='chunks')
    op.drop_index('idx_chunks_doc_topic', table_name='chunks')
    op.drop_index(op.f('ix_chunks_chunk_hash'), table_name='chunks')
    op.drop_index(op.f('ix_chunks_document_id'), table_name='chunks')
    op.drop_index(op.f('ix_chunks_id'), table_name='chunks')
    op.drop_table('chunks')
    
    op.drop_index('idx_page_texts_doc_page', table_name='page_texts')
    op.drop_index(op.f('ix_page_texts_document_id'), table_name='page_texts')
    op.drop_index(op.f('ix_page_texts_id'), table_name='page_texts')
    op.drop_table('page_texts')
    
    op.drop_index(op.f('ix_documents_document_hash'), table_name='documents')
    op.drop_index(op.f('ix_documents_tenant_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_status'), table_name='documents')
    op.drop_index(op.f('ix_documents_pack_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_id'), table_name='documents')
    op.drop_table('documents')
    
    op.drop_index(op.f('ix_content_packs_tenant_id'), table_name='content_packs')
    op.drop_index(op.f('ix_content_packs_id'), table_name='content_packs')
    op.drop_table('content_packs')
    
    # Note: We don't drop the vector extension as it might be used by other tables
