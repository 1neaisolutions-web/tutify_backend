"""
Pydantic schemas for Teacher Tools assignment APIs.

Response fields map to the frontend DemoAssignment shape plus scope fields for hydration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


AssignmentStatus = str  # draft | active | pending_review | graded | archived
DifficultyId = str  # foundation | standard | challenge


class AssignmentBriefLineStub(BaseModel):
    id: str
    text: str = Field(min_length=1)


class AssignmentBriefTopicStub(BaseModel):
    id: str
    title: str = Field(min_length=1)
    lines: List[AssignmentBriefLineStub] = Field(default_factory=list)


# ── Request Schemas ──────────────────────────────────────────────────────────


class AssignmentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=120)
    grade: str = Field(min_length=1, max_length=80)
    classes: List[str] = Field(default_factory=list)
    type: str = Field(default="Structured response", max_length=80)
    rigorProfile: str = Field(default="Standard", max_length=80)
    dueAt: Optional[datetime] = None
    assignedAt: Optional[datetime] = None
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None
    status: AssignmentStatus = "draft"

    sourceBookIds: List[str] = Field(default_factory=list)
    scopeTopics: List[str] = Field(default_factory=list)
    scopeTopicIds: List[str] = Field(default_factory=list)
    scopeRefinement: Optional[str] = None
    generateWithoutSources: bool = False

    difficulty: Optional[DifficultyId] = None

    briefTopics: List[Dict[str, Any]] = Field(default_factory=list)
    handoutLayout: Optional[Dict[str, Any]] = None


class AssignmentPatchRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    subject: Optional[str] = Field(default=None, min_length=1, max_length=120)
    grade: Optional[str] = Field(default=None, min_length=1, max_length=80)
    classes: Optional[List[str]] = None
    type: Optional[str] = Field(default=None, max_length=80)
    rigorProfile: Optional[str] = Field(default=None, max_length=80)
    dueAt: Optional[datetime] = None
    assignedAt: Optional[datetime] = None
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None
    status: Optional[AssignmentStatus] = None

    sourceBookIds: Optional[List[str]] = None
    scopeTopics: Optional[List[str]] = None
    scopeTopicIds: Optional[List[str]] = None
    scopeRefinement: Optional[str] = None
    generateWithoutSources: Optional[bool] = None
    difficulty: Optional[DifficultyId] = None

    briefTopics: Optional[List[Dict[str, Any]]] = None
    handoutLayout: Optional[Dict[str, Any]] = None


class AssignmentGenerateRequest(BaseModel):
    topicCount: int = Field(default=3, ge=1, le=10)
    difficulty: Optional[DifficultyId] = None
    teacherNotes: Optional[str] = None
    rigorProfile: Optional[str] = None


class AssignmentRegenerateTopicRequest(BaseModel):
    topicId: str
    topicTitle: str = Field(min_length=1)


class AssignmentRegenerateLineRequest(BaseModel):
    topicId: str
    topicTitle: str = Field(min_length=1)
    lineIndex: int = Field(ge=0)


# ── Response Schemas ─────────────────────────────────────────────────────────


class AssignmentResponse(BaseModel):
    """Maps to DemoAssignment + RAG/gen fields for edit hydration."""

    id: str
    title: str
    subject: str
    grade: str
    classes: List[str]
    type: str
    dueAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    assignedCount: int
    submitted: int
    pending: int
    graded: int
    status: AssignmentStatus
    topic: str
    sourceSummary: Optional[str] = None
    briefTopics: List[Dict[str, Any]] = Field(default_factory=list)
    studentInstructions: Optional[str] = None
    handoutLayout: Optional[Dict[str, Any]] = None

    sourceBookIds: List[str] = Field(default_factory=list)
    scopeTopics: List[str] = Field(default_factory=list)
    scopeTopicIds: List[str] = Field(default_factory=list)
    scopeRefinement: Optional[str] = None
    generateWithoutSources: bool = False
    rigorProfile: str = "Standard"
    teacherNotes: Optional[str] = None
    difficulty: Optional[str] = None


class AssignmentListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AssignmentResponse]


class AssignmentDuplicateResponse(BaseModel):
    ok: bool = True
    id: str


class AssignmentGenerateResponse(BaseModel):
    ok: bool = True
    generation_run_id: str
    warnings: List[str] = Field(default_factory=list)
    assignment: AssignmentResponse


class RegeneratedTopicResponse(BaseModel):
    ok: bool = True
    topic: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class RegeneratedLineResponse(BaseModel):
    ok: bool = True
    lineId: str
    text: str
    warnings: List[str] = Field(default_factory=list)
