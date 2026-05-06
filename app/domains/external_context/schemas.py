"""
Pydantic schemas for teacher profile context and context resolution.
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field

from app.domains.auth.models import ContextResolutionStatus
from app.domains.personalization.schemas import PersonalizationSyncReceipt


# Resolution status values for API
CONTEXT_RESOLVED = "resolved"
CONTEXT_PARTIAL = "partial"
CONTEXT_NOT_FOUND = "not_found"


class TeacherContextUpdate(BaseModel):
    """Schema for updating teacher professional learning context (PATCH profile)."""

    # Core required
    country: str = Field(..., min_length=1, max_length=100, description="Country")
    region: str = Field(..., min_length=1, max_length=150, description="Region / State / Province")
    school_type: str = Field(..., min_length=1, max_length=50, description="School type")
    grade_band: str = Field(..., min_length=1, max_length=50, description="Grade band")
    subjects: List[str] = Field(..., min_length=1, description="Subjects taught")
    language_preference: str = Field(..., min_length=1, max_length=100, description="Preferred teaching language")

    # Optional (strongly recommended)
    school_name: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    curriculum_framework: Optional[str] = Field(None, max_length=80)
    years_experience: Optional[str] = Field(None, max_length=20)
    professional_goals: Optional[List[str]] = Field(default_factory=list)


class TeacherContextResponse(BaseModel):
    """Response schema for teacher context (in profile)."""

    country: str
    region: str
    school_type: str
    grade_band: str
    subjects: List[str]
    language_preference: str
    school_name: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    curriculum_framework: Optional[str] = None
    years_experience: Optional[str] = None
    professional_goals: Optional[List[str]] = None
    context_resolution_status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProfileUpdateRequest(BaseModel):
    """Full profile update (personal + teaching context) for PATCH /users/profile."""

    # Optional personal fields (only sent if changed)
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    username: Optional[str] = Field(None, max_length=100)

    # Teaching context (optional in request; if present, validated as TeacherContextUpdate)
    teaching_context: Optional[TeacherContextUpdate] = None


class ProfileUpdateResponse(BaseModel):
    """Response for PATCH /users/profile."""

    profile: dict  # UserProfile as dict
    context_resolution_status: str = Field(..., description="resolved | partial | not_found")
    recommendations: Optional[List[str]] = None
    personalization_sync: Optional[PersonalizationSyncReceipt] = None
