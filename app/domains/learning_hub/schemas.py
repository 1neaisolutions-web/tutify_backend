"""
Pydantic schemas for Learning Hub (V1 home orchestration).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Re-export for Learning Hub home response
from app.domains.content_registry.schemas import RecommendationCard  # noqa: F401, E402


# ---------- Profile completeness ----------
class ProfileCompleteness(BaseModel):
    """Deterministic completeness score and missing fields."""

    score: float = Field(..., ge=0.0, le=1.0)
    missing_fields: List[str] = Field(default_factory=list)


class ProfileSectionStatus(BaseModel):
    """Status of a single profile section for the completion gate UI."""
    key: str
    label: str
    complete: bool
    count: int = 0                       # number of records (for identity sections)
    route: str = ""                      # frontend route to complete this section
    description: str = ""               # human-readable hint


class ProfileCompletionStatusResponse(BaseModel):
    """
    GET /api/v1/learning-hub/profile-completion-status

    Returns a structured breakdown the frontend uses to render the
    ProfileCompletionGate — checklist of required sections with CTAs.
    """
    score: float = Field(..., ge=0.0, le=1.0, description="0-1 completeness fraction")
    is_sufficient: bool = Field(..., description="True when score >= 0.45 (warm-start threshold)")
    missing_count: int
    sections: List[ProfileSectionStatus]
    teaching_context_complete: bool
    has_identity_record: bool
    guidance_message: str = ""

    model_config = ConfigDict(from_attributes=False)


# ---------- Teacher summary (from context / CTP) ----------
class TeacherSummary(BaseModel):
    """Summary card from profile context and identity."""

    subjects: List[str] = Field(default_factory=list)
    grade_band: str = ""
    school_type: str = ""
    region: str = ""
    years_experience: str = ""


# ---------- Intelligence (from ml_output when available) ----------
class IntelligenceCard(BaseModel):
    """Intelligence card from pipeline2 or fallback."""

    cluster_id: Optional[str] = None
    persona_tag: Optional[str] = None
    pipeline_version: Optional[str] = None
    feature_schema_version: Optional[str] = None


# ---------- Focus area ----------
class FocusArea(BaseModel):
    """One focus area for the teacher."""

    title: str
    source: str = Field(..., description="ml_output | teacher_context | teacher_identity")
    priority: int = 1


# ---------- Next action ----------
class NextAction(BaseModel):
    """One suggested next action."""

    action_type: str
    label: str
    reason: str


# ---------- Learning Hub home response (V1) ----------
class LearningHubHomeResponse(BaseModel):
    """V1 Learning Hub home payload."""

    teacher_id: UUID
    generated_at: datetime
    profile_completeness: ProfileCompleteness
    teacher_summary: TeacherSummary
    intelligence: IntelligenceCard
    focus_areas: List[FocusArea] = Field(default_factory=list)
    next_actions: List[NextAction] = Field(default_factory=list)
    primary_recommendations: List[RecommendationCard] = Field(default_factory=list)
    secondary_recommendations: List[RecommendationCard] = Field(default_factory=list)
    progress_overview: Optional[Dict[str, Any]] = None
    mode: Literal["cold_start", "warm_start", "personalized"] = "cold_start"

    model_config = ConfigDict(from_attributes=False)
