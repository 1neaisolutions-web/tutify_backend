"""
Pydantic schemas for Teacher Intelligence domain.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- CTP (Comprehensive Teacher Profile) ----------
class CTPIdentity(BaseModel):
    """Identity section of CTP."""

    country: str
    region: str
    subjects: List[str]
    grade_band: str
    language_preference: str


class CTPEnvironment(BaseModel):
    """Environment section of CTP."""

    school_type: str
    curriculum_framework: Optional[str] = None
    years_experience: Optional[str] = None
    school_name: Optional[str] = None


class CTPCareer(BaseModel):
    """Career summary section of CTP."""

    experience_records: int
    current_role: Optional[str] = None
    certifications_count: int
    education_count: int
    achievements_count: int
    documents_count: int


class CTPAssembled(BaseModel):
    """Assembled Comprehensive Teacher Profile (read-only)."""

    teacher_id: UUID
    profile_version: str = "ctp_v1"
    identity: CTPIdentity
    environment: CTPEnvironment
    career: CTPCareer
    goals: List[str] = []

    model_config = ConfigDict(from_attributes=False)


# ---------- Feature Snapshot ----------
class FeatureSnapshotResponse(BaseModel):
    """Feature snapshot response."""

    id: UUID
    teacher_id: UUID
    feature_schema_version: str
    source_hash: str
    generated_at: datetime
    features: Dict[str, Any]
    is_latest: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- ML Output ----------
class MLOutputSaveRequest(BaseModel):
    """Request body for saving ML pipeline output."""

    pipeline_name: str = Field(..., min_length=1, max_length=100)
    pipeline_version: str = Field(..., min_length=1, max_length=50)
    model_version: str = Field(..., min_length=1, max_length=50)
    feature_snapshot_id: Optional[UUID] = None
    results: Dict[str, Any] = Field(...)
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class MLOutputResponse(BaseModel):
    """ML output response."""

    id: UUID
    teacher_id: UUID
    pipeline_name: str
    pipeline_version: str
    model_version: str
    feature_snapshot_id: Optional[UUID] = None
    generated_at: datetime
    results: Dict[str, Any]
    confidence_score: Optional[float] = None
    is_latest: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Pipeline Run ----------
class PipelineRunResponse(BaseModel):
    """Pipeline run response."""

    id: UUID
    teacher_id: UUID
    pipeline_name: str
    pipeline_version: str
    model_version: str
    feature_snapshot_id: Optional[UUID] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    runtime_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
