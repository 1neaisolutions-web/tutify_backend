"""
Pydantic schemas for content ingestion domain.
"""
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator


# Content Pack Schemas
class ContentPackCreate(BaseModel):
    """Create content pack request."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    curriculum: Optional[str] = None
    ocr_policy: Optional[Literal["auto", "math", "non_math"]] = Field(
        default=None,
        description="OCR policy for this pack. auto=use defaults; math=prefer math OCR engines when allowed; non_math=prefer local/general OCR.",
    )
    metadata: Optional[Dict[str, Any]] = None


class ContentPackResponse(BaseModel):
    """Content pack response."""
    id: UUID
    name: str
    description: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    curriculum: Optional[str] = None
    ocr_policy: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # Will be populated from pack_metadata
    is_active: bool
    created_at: datetime
    updated_at: datetime
    document_count: Optional[int] = None  # Added by service
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    @model_validator(mode='before')
    @classmethod
    def map_pack_metadata(cls, data: Any) -> Any:
        """Map pack_metadata to metadata, avoiding SQLAlchemy's built-in metadata attribute."""
        if isinstance(data, dict):
            # If it's already a dict, map pack_metadata to metadata if needed
            if 'pack_metadata' in data and 'metadata' not in data:
                data['metadata'] = data.pop('pack_metadata', None)
            return data
        elif hasattr(data, 'pack_metadata'):
            # If it's a SQLAlchemy model, convert to dict mapping pack_metadata -> metadata
            # This avoids SQLAlchemy's built-in 'metadata' attribute conflict
            return {
                'id': data.id,
                'name': data.name,
                'description': data.description,
                'subject': data.subject,
                'grade': data.grade,
                'curriculum': data.curriculum,
                'ocr_policy': getattr(data, "ocr_policy", None),
                'metadata': data.pack_metadata,  # Map pack_metadata to metadata
                'is_active': data.is_active,
                'created_at': data.created_at,
                'updated_at': data.updated_at,
                'document_count': getattr(data, 'document_count', None),
            }
        return data


class ContentPackListItem(BaseModel):
    """Content pack list item — includes all fields needed for admin CRUD and quiz injection."""
    id: UUID
    name: str
    description: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    curriculum: Optional[str] = None
    is_active: bool
    document_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Document Schemas
class DocumentUpload(BaseModel):
    """Document upload request (metadata only, file via multipart)."""
    pack_id: UUID
    title: Optional[str] = None
    author: Optional[str] = None
    chapter_map: Optional[List[Dict[str, Any]]] = None  # Table of Contents
    force_ocr: bool = False  # Force OCR even if text detected


class DocumentResponse(BaseModel):
    """Document response."""
    id: UUID
    pack_id: UUID
    filename: str
    file_path: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    source_type: str
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    remediation_hint: Optional[str] = None
    processing_metadata: Optional[Dict[str, Any]] = None
    chapter_map: Optional[List[Dict[str, Any]]] = None
    structure_map: Optional[List[Dict[str, Any]]] = None  # Page-range role overrides
    title: Optional[str] = None
    author: Optional[str] = None
    total_pages: Optional[int] = None
    document_hash: Optional[str] = None
    version_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class DocumentListItem(BaseModel):
    """Document list item."""
    id: UUID
    pack_id: UUID
    filename: str
    status: str
    total_pages: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class DocumentStatusResponse(BaseModel):
    """Document status response for SSE streaming."""
    document_id: UUID
    status: str
    progress: Optional["ProcessingProgress"] = None
    steps_completed: List[str] = []
    current_step: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    remediation_hint: Optional[str] = None
    total_pages: Optional[int] = None
    pages_processed: Optional[int] = None


class ProcessingProgress(BaseModel):
    """Processing progress details."""
    step: str
    completed: int
    total: int
    percentage: int
    estimated_time_remaining: Optional[str] = None
    pages_processed: Optional[int] = None
    total_pages: Optional[int] = None


# QA Validation Schemas
class QAValidationRequest(BaseModel):
    """Request to run QA validation."""
    thresholds: Optional[Dict[str, Any]] = None  # Override default thresholds
    golden_queries: Optional[List[str]] = None  # Custom golden queries


class QAValidationResponse(BaseModel):
    """QA validation response."""
    id: UUID
    document_id: UUID
    qa_status: str
    thresholds: Optional[Dict[str, Any]] = None
    golden_query_results: Optional[List[Dict[str, Any]]] = None
    page_coverage_check: Optional[bool] = None
    text_density_check: Optional[bool] = None
    embedding_completeness_check: Optional[bool] = None
    vector_retrieval_check: Optional[bool] = None
    metrics: Optional[Dict[str, Any]] = None
    qa_notes: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# Worksheet Schemas
class WorksheetGenerateRequest(BaseModel):
    """Worksheet generation request."""
    pack_id: UUID  # Primary pack (backward compat). Ignored if pack_ids provided.
    pack_ids: Optional[List[UUID]] = Field(
        default=None,
        description="Optional multi-pack: search across these packs. If set, overrides pack_id for retrieval."
    )
    topic_id: Optional[str] = None
    topic_text: Optional[str] = None  # Alternative to topic_id
    grade: Optional[str] = None
    subject: Optional[str] = None
    difficulty_mix: Optional[Dict[str, float]] = Field(
        default=None,
        description="Difficulty distribution (must sum to 1.0). Ignored if difficulty is set."
    )
    difficulty: Optional[Literal["easy", "medium", "hard"]] = Field(
        default=None,
        description="Single target difficulty. If set, overrides difficulty_mix (100% this level)."
    )
    num_questions: int = Field(default=10, ge=1, le=20, description="Number of questions (1–20).")
    question_types: Optional[List[str]] = Field(
        default=["mcq", "short_answer"],
        description="Question types: mcq, short_answer, long_answer (diagram, matching future)"
    )
    force_regenerate: Optional[bool] = Field(
        default=False,
        description="If True, skip cache and generate a fresh worksheet (for diagnostics/fresh pipeline)"
    )
    skip_cache_write: Optional[bool] = Field(
        default=False,
        description="If True, generate and return worksheet but do not store in cache."
    )
    regenerate_key: Optional[str] = Field(
        default=None,
        description="If set (or force_regenerate=true), generate a new worksheet and avoid repeating/near-duplicate questions from prior worksheets for this user+pack+topic+difficulty."
    )
    teacher_prompt: Optional[str] = Field(
        default=None,
        description="Optional style/constraint instructions appended to the generator prompt. Must not override topic or grade safety."
    )
    teacher_reference_images: Optional[List[str]] = Field(
        default=None,
        description="Placeholder for future: reference image URLs for vision-aware generation. Not implemented."
    )


class WorksheetQuestion(BaseModel):
    """Worksheet question."""
    id: str
    type: str  # mcq, short_answer, essay, diagram, matching
    question: str
    options: Optional[List[str]] = None  # For MCQ
    correct_answer: str
    explanation: Optional[str] = None
    points: int = 1
    difficulty: str  # easy, medium, hard
    math_content: bool = False  # Flag for frontend math rendering


class WorksheetResponse(BaseModel):
    """Worksheet generation response."""
    id: UUID
    pack_id: UUID
    topic_id: Optional[str] = None
    topic_text: Optional[str] = None
    grade: Optional[str] = None
    subject: Optional[str] = None
    questions: List[WorksheetQuestion]
    answer_key: Dict[str, str]  # question_id -> answer
    marking_scheme: Dict[str, Dict[str, Any]]  # question_id -> {points, criteria, etc.}
    citations: Optional[List[Dict[str, str]]] = None  # chunk_id, document_id, page_range
    created_at: Optional[datetime] = None  # None when worksheet not persisted (e.g. cache disabled)
    # Optional retrieval diagnostics (for topic-alignment checks)
    chapter_page_range: Optional[str] = None
    relevance_avg_sim: Optional[float] = None
    relevance_keyword_hits: Optional[int] = None
    # Difficulty handling (only when difficulty was requested on generate)
    final_difficulty_used: Optional[str] = None  # easy | medium | hard
    attempts_count: Optional[int] = None  # alias: attempts (for API consistency)
    attempts: Optional[int] = None  # same as attempts_count; populated from it
    validator_report_per_attempt: Optional[List[str]] = None
    validator_reports: Optional[List[str]] = None  # optional debug alias
    warnings: Optional[List[str]] = None

    @field_validator("citations", mode="before")
    @classmethod
    def citations_must_be_list(cls, v: Any) -> Optional[List[Dict[str, str]]]:
        """Coerce citations to list: accept list, or dict (e.g. retrieval_metadata) -> use .get('citations', [])."""
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            c = v.get("citations")
            return c if isinstance(c, list) else []
        return []


# Document Processing Run Schemas
class DocumentProcessingRunResponse(BaseModel):
    """Document processing run response."""
    id: UUID
    document_id: UUID
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    remediation_hint: Optional[str] = None
    progress_percentage: Optional[int] = None
    current_step: Optional[str] = None
    completed_steps: Optional[List[str]] = None
    pages_processed: Optional[int] = None
    chunks_created: Optional[int] = None
    vectors_stored: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# Update forward references
DocumentStatusResponse.model_rebuild()
