"""Pydantic schemas for the personalization domain API contracts."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.domains.personalization.enums import (
    AssignmentBucket,
    AssignmentStatus,
    PersonalizationJobStatus,
    PersonalizationJobType,
    PersonalizationStatus,
    ProfileChangeSeverity,
    SectionReadinessStatus,
)


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class PersonalizationSyncReceipt(BaseModel):
    """Returned after profile/identity mutations that enqueue personalization work."""

    status: str = Field(..., description="queued | noop")
    operation: str = Field(..., description="recompute | reset | start | noop")
    severity: str = Field("none", description="major_reset | minor_recompute | none")
    changed_fields: list[str] = Field(default_factory=list, description="Profile fields that changed")
    message: str = Field("", description="Human-readable description of what will happen")
    personalization_version: int = 0
    last_recomputed_at: Optional[str] = Field(None, description="ISO timestamp at enqueue time for client polling")
    correlation_id: str = ""


class SectionReadinessOut(BaseModel):
    section: str
    status: SectionReadinessStatus
    visible_count_target: int
    visible_count_actual: int
    last_ready_at: Optional[datetime] = None
    failure_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Personalization State
# ---------------------------------------------------------------------------

class PersonalizationStateOut(BaseModel):
    """GET /api/v1/personalization/state response."""
    user_id: uuid.UUID
    status: PersonalizationStatus
    personalization_version: int
    profile_completeness: float
    personalization_started_at: Optional[datetime] = None
    last_recomputed_at: Optional[datetime] = None
    last_reset_at: Optional[datetime] = None
    section_readiness: list[SectionReadinessOut] = Field(default_factory=list)
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StartPersonalizationRequest(BaseModel):
    """POST /api/v1/personalization/start request."""
    trigger: Optional[str] = "user_request"


class StartPersonalizationResponse(BaseModel):
    status: str
    personalization_version: int
    message: str


class ResetPersonalizationRequest(BaseModel):
    """POST /api/v1/personalization/reset request."""
    reason: Optional[str] = None
    confirmed: bool = False


class ResetPersonalizationResponse(BaseModel):
    status: str
    new_version: int
    message: str


# ---------------------------------------------------------------------------
# Slate / Home sections
# ---------------------------------------------------------------------------

class SlateCardOut(BaseModel):
    """A single card emitted by the slate for frontend rendering."""
    assignment_id: uuid.UUID
    content_id: str
    content_type: str
    section: str
    bucket: AssignmentBucket
    position: int
    locked: bool
    title: Optional[str] = None
    route: Optional[str] = None
    content_slug: Optional[str] = None
    score: float = 0.0
    reason_codes: list[str] = Field(default_factory=list)
    display_meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SectionSlateOut(BaseModel):
    section: str
    readiness: SectionReadinessStatus
    visible_items: list[SlateCardOut] = Field(default_factory=list)
    locked_preview_items: list[SlateCardOut] = Field(default_factory=list)
    message: Optional[str] = None


class LearningHubSlateResponse(BaseModel):
    """Modified GET /api/v1/learning-hub/home response when personalization is active."""
    mode: str  # personalized | initializing | partial_ready | no_profile
    personalization_version: int
    sections: dict[str, SectionSlateOut] = Field(default_factory=dict)
    global_message: Optional[str] = None
    last_recomputed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class PersonalizationJobOut(BaseModel):
    id: uuid.UUID
    job_type: PersonalizationJobType
    status: PersonalizationJobStatus
    section: Optional[str] = None
    trigger: Optional[str] = None
    retry_count: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Unlock
# ---------------------------------------------------------------------------

class UnlockStateOut(BaseModel):
    assignment_id: uuid.UUID
    section: str
    locked: bool
    bucket: AssignmentBucket
    unlocked_at: Optional[datetime] = None
    unlock_rule_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UnlockRuleOut(BaseModel):
    rule_id: str
    section: str
    batch_order: int
    trigger_type: str
    trigger_section: str
    trigger_threshold: int
    unlock_count: int
    unlock_selection: str
    cooldown_seconds: int
    enabled: bool
    priority: int
    rule_metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UnlockRuleUpdateRequest(BaseModel):
    trigger_threshold: Optional[int] = None
    unlock_count: Optional[int] = None
    enabled: Optional[bool] = None
    cooldown_seconds: Optional[int] = None
    priority: Optional[int] = None


# ---------------------------------------------------------------------------
# Activity Events
# ---------------------------------------------------------------------------

class ActivityEventIn(BaseModel):
    client_event_id: str
    event_type: str
    section: Optional[str] = None
    content_id: Optional[str] = None
    content_type: Optional[str] = None
    assignment_id: Optional[uuid.UUID] = None
    slate_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    dwell_ms: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityEventsRequest(BaseModel):
    events: list[ActivityEventIn]


class ActivityEventsResponse(BaseModel):
    accepted: int
    duplicate_skipped: int


# ---------------------------------------------------------------------------
# Content Completion
# ---------------------------------------------------------------------------

class ContentCompleteRequest(BaseModel):
    assignment_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    progress_percent: float = 100.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentCompleteResponse(BaseModel):
    assignment_id: Optional[uuid.UUID] = None
    status: str
    newly_unlocked: list[uuid.UUID] = Field(default_factory=list)
    message: str


# ---------------------------------------------------------------------------
# Profile change severity
# ---------------------------------------------------------------------------

class ProfileChangeSeverityRequest(BaseModel):
    current_profile: dict[str, Any]
    proposed_profile: dict[str, Any]


class ProfileChangeSeverityResponse(BaseModel):
    severity: ProfileChangeSeverity
    changed_fields: list[str]
    message: str


# ---------------------------------------------------------------------------
# Preflight impact check (read-only, no side effects)
# ---------------------------------------------------------------------------

class ProfilePreflightRequest(BaseModel):
    """
    Proposed teaching context payload to evaluate BEFORE saving.
    Keys match TeacherProfileContext fields.  Only include fields the user is changing.
    """
    proposed_context: dict[str, Any] = Field(..., description="Proposed teaching-context fields (partial OK)")


class ProfilePreflightResponse(BaseModel):
    """
    Impact summary for the proposed profile change — no DB writes, no jobs enqueued.
    """
    severity: str = Field(..., description="major_reset | minor_recompute | none")
    operation: str = Field(..., description="reset | recompute | start | noop")
    changed_fields: list[str] = Field(default_factory=list)
    message: str = ""
    user_display_title: str = ""
    user_display_body: str = ""
    requires_confirmation: bool = False


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class AdminPersonalizationOverviewResponse(BaseModel):
    total_personalized_users: int
    users_by_status: dict[str, int]
    section_readiness_heatmap: dict[str, dict[str, int]]
    jobs_last_24h: dict[str, int]
    avg_time_to_first_content_seconds: Optional[float] = None
    avg_time_to_full_readiness_seconds: Optional[float] = None
    unlock_conversion_rate_30d: Optional[float] = None
    pool_depletion_alerts: list[dict[str, Any]] = Field(default_factory=list)
    recent_orchestration_errors: list[dict[str, Any]] = Field(default_factory=list)
    banner_trigger_stats: dict[str, int] = Field(default_factory=dict)
