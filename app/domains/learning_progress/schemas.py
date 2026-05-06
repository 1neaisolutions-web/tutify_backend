"""Pydantic schemas for Learning Progress domain."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- Learning sessions ----------
class LearningSessionCreate(BaseModel):
    content_id: str = Field(..., max_length=150)
    content_type: str = Field(..., max_length=50)
    locale: Optional[str] = Field(None, max_length=20)
    session_metadata: Dict[str, Any] = Field(default_factory=dict)


class LearningSessionUpdate(BaseModel):
    progress_percent: Optional[float] = None
    duration_seconds: Optional[int] = None
    session_status: Optional[str] = None
    session_metadata: Optional[Dict[str, Any]] = None


class LearningSessionResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    content_id: str
    content_type: str
    session_status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    progress_percent: float
    duration_seconds: int
    last_event_at: Optional[datetime] = None
    locale: Optional[str] = None
    session_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningSessionListItem(BaseModel):
    id: UUID
    content_id: str
    content_type: str
    session_status: str
    progress_percent: float
    duration_seconds: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Learning events ----------
class LearningEventCreate(BaseModel):
    session_id: UUID
    content_id: str = Field(..., max_length=150)
    event_type: str = Field(..., max_length=50)
    event_metadata: Dict[str, Any] = Field(default_factory=dict)


class LearningEventResponse(BaseModel):
    id: UUID
    session_id: UUID
    teacher_id: UUID
    content_id: str
    event_type: str
    event_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Recommendation events ----------
class RecommendationEventCreate(BaseModel):
    content_id: str = Field(..., max_length=150)
    content_type: Optional[str] = Field(None, max_length=50)
    recommendation_source: Optional[str] = Field(None, max_length=100)
    event_type: str = Field(..., max_length=50)
    event_metadata: Dict[str, Any] = Field(default_factory=dict)


class RecommendationEventResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    content_id: str
    content_type: Optional[str] = None
    recommendation_source: Optional[str] = None
    event_type: str
    event_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Content feedback ----------
class ContentFeedbackCreate(BaseModel):
    content_id: str = Field(..., max_length=150)
    rating: Optional[int] = Field(None, ge=1, le=5)
    difficulty_feedback: Optional[str] = Field(None, max_length=50)
    usefulness_feedback: Optional[str] = Field(None, max_length=50)
    comment: Optional[str] = None
    feedback_metadata: Dict[str, Any] = Field(default_factory=dict)


class ContentFeedbackResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    content_id: str
    rating: Optional[int] = None
    difficulty_feedback: Optional[str] = None
    usefulness_feedback: Optional[str] = None
    comment: Optional[str] = None
    feedback_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Aggregations ----------
class ContentProgressSummary(BaseModel):
    content_id: str
    total_sessions: int
    completed_sessions: int
    in_progress_sessions: int
    total_learning_minutes: int
    last_activity_at: Optional[datetime] = None
    progress_percent: float = 0.0


class LearningProgressOverview(BaseModel):
    total_sessions: int
    completed_content_count: int
    in_progress_content_count: int
    total_learning_minutes: int
    last_activity_at: Optional[datetime] = None

