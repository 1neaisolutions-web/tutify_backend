"""
Pydantic schemas for Template models, universal input, and universal output.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
import enum

from pydantic import BaseModel, Field

from app.models.template import TemplateCategory
from app.models.template_version import TemplateVersionStatus


# ---- Universal Input Models ----


class Subject(str, enum.Enum):
    """Universal subject enumeration."""

    ENGLISH = "english"
    MATH = "math"
    SCIENCE = "science"
    SOCIAL_STUDIES = "social_studies"
    STEAM = "steam"
    OTHER = "other"


class GradeBand(str, enum.Enum):
    """Universal grade band enumeration."""

    K_2 = "K-2"
    THREE_FIVE = "3-5"
    SIX_EIGHT = "6-8"
    NINE_TWELVE = "9-12"


class BloomLevel(str, enum.Enum):
    """Bloom's taxonomy levels."""

    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class LanguageLevel(str, enum.Enum):
    """Language proficiency levels."""

    EMERGING = "emerging"
    DEVELOPING = "developing"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"


class UniversalTemplateInput(BaseModel):
    """
    Universal input structure shared across templates.

    Template-specific fields are represented in TemplateVersion.input_schema
    and carried in the execution data payload.
    """

    subject: Subject
    grade_band: GradeBand
    topic: str
    learning_objective: str
    time_duration_minutes: int
    bloom_level: BloomLevel
    differentiation_notes: Optional[str] = None
    language_level: Optional[LanguageLevel] = None


# ---- Universal Output Models ----


class LessonStep(BaseModel):
    """Single lesson or activity step."""

    title: str
    description: str


class BloomAlignmentItem(BaseModel):
    """Alignment item to Bloom's taxonomy."""

    level: BloomLevel
    description: str


class AssessmentQuestion(BaseModel):
    """Question structure for assessment templates."""

    question_text: str
    type: str
    answer_key: Optional[str] = None
    difficulty: Optional[str] = None


class AssessmentSection(BaseModel):
    """Assessment section for universal output."""

    checks_for_understanding: List[str]
    rubric: Optional[Dict[str, Any]] = None


class CommunicationSection(BaseModel):
    """Communication-specific output fields."""

    subject_line: Optional[str] = None
    message_body: Optional[str] = None
    key_details: Optional[List[str]] = None
    call_to_action: Optional[str] = None


class UniversalTemplateOutput(BaseModel):
    """
    Universal output container used by all templates.

    Some fields (e.g. questions, communication) are only populated for certain
    template categories.
    """

    overview: str
    learning_goals: List[str]
    materials: List[str]
    steps: List[LessonStep]
    differentiation: List[str] = Field(default_factory=list)
    assessment: Optional[AssessmentSection] = None
    teacher_notes: List[str] = Field(default_factory=list)
    bloom_alignment: List[BloomAlignmentItem] = Field(default_factory=list)

    # For assessment templates
    questions: Optional[List[AssessmentQuestion]] = None

    # For communication templates
    communication: Optional[CommunicationSection] = None


def get_universal_output_json_schema() -> Dict[str, Any]:
    """
    Return full JSON Schema for UniversalTemplateOutput.

    Used when seeding template versions so each version stores the output structure.
    Enables per-template output schema changes later (edit version.output_schema).
    """
    return UniversalTemplateOutput.model_json_schema()


# ---- Template Schemas ----


class TemplateListItem(BaseModel):
    """Schema for template list items."""

    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    category: TemplateCategory
    subject_default: Optional[str] = None
    grade_bands_supported: Optional[List[str]] = None
    is_active: bool
    is_hot: bool = False  # Top 3 by execution count
    is_favorite: bool = False  # Whether current user/session has favorited this
    execution_count: int = 0  # Total execution count for popularity

    class Config:
        from_attributes = True


class TemplateVersionPublic(BaseModel):
    """Schema for public template version information."""

    id: UUID
    version: int
    status: TemplateVersionStatus
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    prompt_definition: Optional[Dict[str, Any]] = None
    llm_model_config: Optional[Dict[str, Any]] = Field(default=None, alias="model_config")
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class TemplateRenderSection(BaseModel):
    """Section metadata for streaming / exemplar preview (from templates/{slug}.json)."""

    key: str
    label: str
    type: str = "markdown"


class TemplateDetail(BaseModel):
    """Schema for detailed template information."""

    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    category: TemplateCategory
    subject_default: Optional[str] = None
    grade_bands_supported: Optional[List[str]] = None
    is_system_template: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_version: Optional[TemplateVersionPublic] = None
    render_sections: Optional[List[TemplateRenderSection]] = None

    class Config:
        from_attributes = True


# ---- Template Execution Schemas ----


class TemplateExecuteRequest(BaseModel):
    """Schema for template execution request."""

    data: Dict[str, Any] = Field(
        ...,
        description="Input data matching the template's input_schema (includes universal and template-specific fields).",
    )


class TemplateExecuteResponse(BaseModel):
    """Schema for template execution response. Output shape is per-template (from output_schema)."""

    execution_id: UUID
    template_id: UUID
    template_version: int
    output: Dict[str, Any] = Field(
        ...,
        description="Output dict; structure is defined by the template's output_schema.",
    )
    model_used: Optional[str] = None
    provider_used: Optional[str] = None
    token_usage: Optional[Dict[str, int]] = None
    latency_ms: Optional[int] = None

    class Config:
        from_attributes = True
