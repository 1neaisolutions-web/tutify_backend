"""
Content Ingestion domain models.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON,
    Index, UniqueConstraint, Numeric
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.base_class import Base
from app.domains.content_ingestion.enums import DocumentStatus, QAStatus, SourceType


class ContentPack(Base):
    """Content pack model for organizing curriculum documents."""

    __tablename__ = "content_packs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    subject = Column(String(100), nullable=True)  # Mathematics, English, etc.
    grade = Column(String(50), nullable=True)  # Grade 5, Grade 6-8, etc.
    curriculum = Column(String(100), nullable=True)  # Cambridge, IB, CCSS, etc.
    
    # Metadata (renamed to pack_metadata to avoid SQLAlchemy reserved name conflict)
    pack_metadata = Column('metadata', JSONB, nullable=True)  # Additional metadata as JSON
    
    # OCR policy: math | non_math | auto (default auto for backward compatibility)
    ocr_policy = Column(String(50), nullable=True, default="auto")
    
    # Ownership
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    documents = relationship("Document", back_populates="pack", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<ContentPack(id={self.id}, name={self.name})>"


class Document(Base):
    """Document model for uploaded curriculum content."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    pack_id = Column(UUID(as_uuid=True), ForeignKey("content_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # File information
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)  # Storage path
    file_size = Column(Integer, nullable=True)  # Size in bytes
    mime_type = Column(String(100), nullable=True)
    source_type = Column(String(20), nullable=False)  # pdf, docx, image, text
    
    # Processing status
    status = Column(String(50), nullable=False, default=DocumentStatus.UPLOADED.value, index=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    remediation_hint = Column(Text, nullable=True)
    
    # Processing metadata
    processing_metadata = Column(JSONB, nullable=True)  # ocr_mode, ocr_engine, chunk_size, embedding_model, etc.
    
    # Chapter map (Table of Contents)
    chapter_map = Column(JSONB, nullable=True)  # Array of {id, title, level, parent_id, start_page, end_page, keywords}
    # Structure map: page-range-based role overrides for role tagging (board-agnostic)
    structure_map = Column(JSONB, nullable=True)  # e.g. [{"page_start": 10, "page_end": 15, "role": "worked_example"}]
    
    # Document metadata
    title = Column(String(500), nullable=True)
    author = Column(String(200), nullable=True)
    total_pages = Column(Integer, nullable=True)
    document_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hash for deduplication
    
    # Version tracking
    version_label = Column(String(50), nullable=True)
    
    # Ownership
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)  # When processing completed
    
    # Relationships
    pack = relationship("ContentPack", back_populates="documents")
    pages = relationship("PageText", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    processing_runs = relationship("DocumentProcessingRun", back_populates="document", cascade="all, delete-orphan")
    qa_validations = relationship("QAValidation", back_populates="document", cascade="all, delete-orphan")
    math_blocks = relationship("MathBlock", back_populates="document", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"


class MathBlock(Base):
    """Math block extracted from a document page (equation, expression, etc.)."""

    __tablename__ = "math_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_no = Column(Integer, nullable=False)
    block_type = Column(String(50), nullable=False)  # equation, expression, table, unknown
    raw_text = Column(Text, nullable=True)
    normalized_text = Column(Text, nullable=True)
    bbox_json = Column(JSONB, nullable=True)
    confidence = Column(Numeric(5, 2), nullable=True)
    provider_name = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("Document", back_populates="math_blocks")

    __table_args__ = (
        Index("idx_math_blocks_doc_page", "document_id", "page_no"),
    )

    def __repr__(self) -> str:
        return f"<MathBlock(id={self.id}, document_id={self.document_id}, page_no={self.page_no})>"


class PageText(Base):
    """Per-page extracted text from documents."""

    __tablename__ = "page_texts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    page_no = Column(Integer, nullable=False)  # 1-indexed page number
    text = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    
    # OCR metadata (if OCR was used)
    ocr_confidence = Column(Numeric(5, 2), nullable=True)  # 0.00 to 1.00
    ocr_engine = Column(String(50), nullable=True)  # tesseract, mathpix, etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="pages")
    
    # Indexes
    __table_args__ = (
        Index("idx_page_texts_doc_page", "document_id", "page_no"),
    )
    
    def __repr__(self) -> str:
        return f"<PageText(id={self.id}, document_id={self.document_id}, page_no={self.page_no})>"


class Chunk(Base):
    """Text chunks with embeddings for vector search."""

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Chunk identification
    chunk_id = Column(String(100), nullable=False)  # Unique within document
    chunk_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hash of text
    
    # Text content
    text = Column(Text, nullable=False)
    
    # Page range
    page_start_pdf = Column(Integer, nullable=True)  # Starting page (1-indexed)
    page_end_pdf = Column(Integer, nullable=True)  # Ending page (1-indexed)
    
    # Chapter/topic mapping
    topic_id = Column(String(100), nullable=True, index=True)  # From chapter_map
    topic_title = Column(String(500), nullable=True)
    
    # Embedding (legacy: fixed 1536 for backwards compatibility)
    embedding = Column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small dimension
    embedding_model = Column(String(100), nullable=True)  # text-embedding-3-small, etc.
    # Dimension-safe embedding (active for free/local providers)
    embedding_v = Column(Vector(1536), nullable=True)  # Variable-dim; stored with zero-pad up to 1536
    embedding_dim = Column(Integer, nullable=True)  # Actual dimension (e.g. 384, 1536)
    embedding_provider = Column(String(100), nullable=True)  # fake, local, openai
    
    # Metadata
    metadata_json = Column(JSONB, nullable=True)  # Additional chunk metadata
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    # Indexes
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_id", name="uq_chunks_doc_chunk"),
        Index("idx_chunks_doc_topic", "document_id", "topic_id"),
        Index("idx_chunks_embedding", "embedding", postgresql_using="ivfflat", postgresql_with={"lists": 100}),
    )
    
    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, document_id={self.document_id}, chunk_id={self.chunk_id})>"


class DocumentProcessingRun(Base):
    """Processing run history for documents."""

    __tablename__ = "document_processing_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Run status
    status = Column(String(50), nullable=False)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    remediation_hint = Column(Text, nullable=True)
    
    # Processing details
    ocr_mode = Column(String(50), nullable=True)  # auto, forced, skipped
    ocr_engine = Column(String(50), nullable=True)
    chunk_size_tokens = Column(Integer, nullable=True)
    overlap_tokens = Column(Integer, nullable=True)
    embedding_model = Column(String(100), nullable=True)
    index_namespace = Column(String(100), nullable=True)
    
    # Progress tracking
    progress_percentage = Column(Integer, nullable=True)  # 0-100
    current_step = Column(String(100), nullable=True)
    completed_steps = Column(JSONB, nullable=True)  # Array of completed step names
    
    # Statistics
    pages_processed = Column(Integer, nullable=True)
    chunks_created = Column(Integer, nullable=True)
    vectors_stored = Column(Integer, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    document = relationship("Document", back_populates="processing_runs")
    
    def __repr__(self) -> str:
        return f"<DocumentProcessingRun(id={self.id}, document_id={self.document_id}, status={self.status})>"


class QAValidation(Base):
    """QA validation results for documents."""

    __tablename__ = "qa_validations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Validation status
    qa_status = Column(String(50), nullable=False, default=QAStatus.PENDING.value)
    
    # Thresholds used
    thresholds = Column(JSONB, nullable=True)  # {min_chars_per_page, max_empty_pages_pct, min_embedding_completeness, etc.}
    
    # Test results
    golden_query_results = Column(JSONB, nullable=True)  # Array of {query, top_k, chunk_ids, similarity_scores, passed}
    page_coverage_check = Column(Boolean, nullable=True)  # All pages processed?
    text_density_check = Column(Boolean, nullable=True)  # Meets min chars/page?
    embedding_completeness_check = Column(Boolean, nullable=True)  # All chunks embedded?
    vector_retrieval_check = Column(Boolean, nullable=True)  # Golden queries pass?
    
    # Metrics
    metrics = Column(JSONB, nullable=True)  # {avg_chars_per_page, empty_pages_pct, embedding_completeness_pct, etc.}
    
    # Review information
    qa_notes = Column(Text, nullable=True)
    qa_reviewer = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    document = relationship("Document", back_populates="qa_validations")
    
    def __repr__(self) -> str:
        return f"<QAValidation(id={self.id}, document_id={self.document_id}, qa_status={self.qa_status})>"


class WorksheetCache(Base):
    """Cached worksheet generation results."""

    __tablename__ = "worksheet_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Cache key (signature hash)
    signature_hash = Column(String(64), nullable=False, unique=True, index=True)  # Hash of (pack_id, topic, difficulty, num_questions, format_version)
    
    # Generation parameters
    pack_id = Column(UUID(as_uuid=True), ForeignKey("content_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id = Column(String(100), nullable=True, index=True)
    topic_text = Column(String(500), nullable=True)
    grade = Column(String(50), nullable=True)
    subject = Column(String(100), nullable=True)
    difficulty_mix = Column(JSONB, nullable=True)  # {easy: 0.3, medium: 0.5, hard: 0.2}
    num_questions = Column(Integer, nullable=False)
    format_version = Column(String(20), nullable=False, default="1.0")
    
    # Cached result
    worksheet_json = Column(JSONB, nullable=False)  # Full worksheet JSON
    
    # Metadata
    chunk_ids_used = Column(JSONB, nullable=True)  # Array of chunk IDs used for generation
    retrieval_metadata = Column(JSONB, nullable=True)  # {query_vector, top_k, similarity_scores, etc.}
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Optional: for regenerate dedupe (last worksheet per user+pack+topic)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    def __repr__(self) -> str:
        return f"<WorksheetCache(id={self.id}, signature_hash={self.signature_hash})>"


class WorksheetQuestionHash(Base):
    """Stores question hashes per user+pack+topic+difficulty for regeneration deduplication."""

    __tablename__ = "worksheet_question_hashes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    pack_id = Column(UUID(as_uuid=True), ForeignKey("content_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_signature = Column(String(64), nullable=False, index=True)  # hash of topic_id/topic_text + grade + subject
    difficulty = Column(String(20), nullable=True, index=True)  # easy | medium | hard
    question_hash = Column(String(64), nullable=False, index=True)  # sha256 of normalized question text
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (Index("ix_wqh_user_pack_topic_diff", "user_id", "pack_id", "topic_signature", "difficulty"),)
