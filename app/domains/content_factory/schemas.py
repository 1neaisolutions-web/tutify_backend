"""
Pydantic schemas for Content Factory domain.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- Request ----------
class GenerateMicroCourseRequest(BaseModel):
    """Request to generate a new micro-course."""

    topic: str = Field(..., min_length=1, max_length=255)
    subject: Optional[str] = Field(None, max_length=100)
    grade_band: Optional[str] = Field(None, max_length=50)
    difficulty: Optional[str] = Field(None, max_length=50)
    locale: str = Field(default="en", max_length=20)
    generation_mode: str = Field(
        default="on_demand",
        description="on_demand runs the workflow synchronously; gap_detection enqueues an async gap job for the background worker.",
    )

    @field_validator("generation_mode")
    @classmethod
    def _validate_generation_mode(cls, v: str) -> str:
        allowed = {"on_demand", "gap_detection"}
        vv = str(v).strip().lower()
        if vv not in allowed:
            raise ValueError(f"Invalid generation_mode. Allowed: {sorted(allowed)}")
        return vv


# ---------- Job ----------
class ContentGenerationJobResponse(BaseModel):
    """Full job response for detail view."""

    id: UUID
    requested_by_user_id: Optional[UUID] = None
    content_type: str
    job_type: str = "micro_course"
    generation_strategy: str
    topic: str
    subject: Optional[str] = None
    grade_band: Optional[str] = None
    difficulty: Optional[str] = None
    locale: str
    source: Optional[str] = None
    status: str
    current_step: Optional[str] = None
    retry_count: int = 0
    priority: int = 0
    quality_score: Optional[float] = None
    result_content_id: Optional[str] = None
    error_message: Optional[str] = None
    step_outputs: Dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    publication_policy_decision: Optional[str] = None
    approved_by_user_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("review_required", mode="before")
    @classmethod
    def _coerce_review_required_detail(cls, v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        try:
            return int(v) != 0
        except (TypeError, ValueError):
            return bool(v)


class ContentFactoryJobsSummaryResponse(BaseModel):
    """Aggregate job/registry counts for admin operations."""

    pending_count: int = 0
    running_count: int = 0
    reviewing_count: int = 0
    awaiting_human_approval_count: int = 0
    publishing_count: int = 0
    failed_count: int = 0
    rejected_count: int = 0
    completed_count: int = 0
    stuck_count: int = 0
    stuck_threshold_hours: int = Field(
        2,
        description="Jobs in pending/running with updated_at older than this (hours) count as stuck.",
    )
    published_generated_count: int = Field(
        0,
        description="Published registry items with source_type=content_factory.",
    )


class StopGenerationResponse(BaseModel):
    """Response for stopping background generation."""

    worker_cancelled: bool = False
    pending_jobs_stopped: int = 0
    message: str = "OK"


class ContentGenerationJobListItem(BaseModel):
    """Job list item (subset)."""

    id: UUID
    content_type: str
    job_type: str = "micro_course"
    generation_strategy: str = "topic_based"
    topic: str
    subject: Optional[str] = None
    grade_band: Optional[str] = None
    locale: str = "en"
    source: Optional[str] = None
    status: str
    current_step: Optional[str] = None
    priority: int = 0
    quality_score: Optional[float] = None
    result_content_id: Optional[str] = None
    error_message: Optional[str] = None
    review_required: bool = False
    publication_policy_decision: Optional[str] = Field(
        None,
        description="auto_publish | require_approval | rejected — surfaced for admin visibility.",
    )
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("review_required", mode="before")
    @classmethod
    def _coerce_review_required(cls, v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        try:
            return int(v) != 0
        except (TypeError, ValueError):
            return bool(v)


# ---------- Agent output shapes (for validation / typing) ----------
class CurriculumOutput(BaseModel):
    """Output schema from curriculum agent."""

    learning_objectives: List[str] = Field(default_factory=list)
    key_concepts: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    target_skills: List[str] = Field(default_factory=list)


class PedagogyOutput(BaseModel):
    """Output schema from pedagogy agent."""

    instructional_flow: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    teaching_strategies: List[str] = Field(default_factory=list)
    teacher_reflections: List[str] = Field(default_factory=list)


class StructureOutput(BaseModel):
    """Output schema from structure agent (micro-course structure)."""

    modules: List[Dict[str, Any]] = Field(default_factory=list)
    lessons: List[Dict[str, Any]] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    activities: List[Dict[str, Any]] = Field(default_factory=list)


class AssessmentOutput(BaseModel):
    """Output schema from assessment agent."""

    practice_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    reflection_prompts: List[str] = Field(default_factory=list)
    mini_quizzes: List[Dict[str, Any]] = Field(default_factory=list)
    rubrics: List[Dict[str, Any]] = Field(default_factory=list)


class ReviewOutput(BaseModel):
    """Output schema from review agent."""

    review_status: str = "pending"
    issues_found: List[str] = Field(default_factory=list)
    improvement_notes: List[str] = Field(default_factory=list)


class QualityOutput(BaseModel):
    """Output schema from quality agent."""

    quality_score: float = 0.0
    quality_feedback: str = ""
    clarity: Optional[float] = None
    pedagogical_depth: Optional[float] = None
    teacher_usefulness: Optional[float] = None
    structure_quality: Optional[float] = None


# ---------- Review schemas ----------
class ContentGenerationReviewResponse(BaseModel):
    """Response schema for a single review record."""

    id: UUID
    job_id: UUID
    reviewer_user_id: Optional[UUID] = None
    decision: str
    notes: Optional[str] = None
    review_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewActionRequest(BaseModel):
    """Request body for approve / reject / request-changes."""

    notes: Optional[str] = None
