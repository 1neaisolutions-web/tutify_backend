from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

OutputFormat = Literal["printable_pdf", "interactive_digital", "both"]
WorksheetStatus = Literal["draft", "published", "archived"]
WorksheetBlockType = Literal["mcq", "fill_blank", "short", "match"]
DifficultyId = Literal["foundation", "standard", "challenge"]


class WorksheetBlockResponse(BaseModel):
    id: str
    type: WorksheetBlockType
    prompt: Optional[str] = None
    points: float
    options: Optional[List[str]] = None
    answer: Optional[str] = None
    sampleAnswer: Optional[str] = None
    responseLines: Optional[int] = None
    left: Optional[List[str]] = None
    right: Optional[List[str]] = None


class WorksheetSessionResponse(BaseModel):
    id: str
    sortOrder: int
    title: str
    blocks: List[WorksheetBlockResponse]


class WorksheetApiResponse(BaseModel):
    id: str
    title: str
    subject: str
    grade: str
    outputFormat: OutputFormat
    classes: List[str]
    status: WorksheetStatus
    assignedAt: Optional[datetime] = None
    dueAt: Optional[datetime] = None
    sessions: List[WorksheetSessionResponse]
    sessionsCount: int
    blocksCount: int
    submissionCount: int
    avgScore: float
    topic: str
    sourceBookIds: List[str]
    scopeTopics: List[str]
    scopeTopicIds: List[str] = Field(default_factory=list)
    scopeRefinement: Optional[str] = None
    sourceSummary: Optional[str] = None
    difficulty: Optional[str] = None
    handoutLayout: Optional[Dict[str, Any]] = None
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None
    generateWithoutSources: bool = False
    createdAt: datetime
    updatedAt: datetime


class WorksheetListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[WorksheetApiResponse]


class WorksheetCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=120)
    grade: str = Field(min_length=1, max_length=80)
    outputFormat: OutputFormat = "interactive_digital"
    classes: List[str] = Field(default_factory=list)
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None
    status: WorksheetStatus = "draft"
    sourceBookIds: List[str] = Field(default_factory=list)
    scopeTopics: List[str] = Field(default_factory=list)
    scopeTopicIds: List[str] = Field(default_factory=list)
    scopeRefinement: Optional[str] = None
    generateWithoutSources: bool = False
    difficulty: Optional[DifficultyId] = None
    handoutLayout: Optional[Dict[str, Any]] = None


class WorksheetPatchRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    subject: Optional[str] = Field(default=None, min_length=1, max_length=120)
    grade: Optional[str] = Field(default=None, min_length=1, max_length=80)
    outputFormat: Optional[OutputFormat] = None
    classes: Optional[List[str]] = None
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None
    status: Optional[WorksheetStatus] = None
    assignedAt: Optional[datetime] = None
    dueAt: Optional[datetime] = None
    sourceBookIds: Optional[List[str]] = None
    scopeTopics: Optional[List[str]] = None
    scopeTopicIds: Optional[List[str]] = None
    scopeRefinement: Optional[str] = None
    generateWithoutSources: Optional[bool] = None
    difficulty: Optional[DifficultyId] = None
    handoutLayout: Optional[Dict[str, Any]] = None


class WorksheetGenerateRequest(BaseModel):
    questionCount: int = Field(default=10, ge=1, le=60)
    mixMode: Literal["balanced", "custom"] = "balanced"
    includeMcq: bool = True
    includeFillBlank: bool = True
    includeShort: bool = True
    includeMatch: bool = True
    countsByType: Optional[Dict[str, int]] = None
    difficulty: Optional[DifficultyId] = None
    teacherNotes: Optional[str] = None


class WorksheetGenerateResponse(BaseModel):
    ok: bool = True
    generation_run_id: str
    warnings: List[str] = Field(default_factory=list)
    worksheet: WorksheetApiResponse


class WorksheetSessionCreateRequest(BaseModel):
    title: str = Field(default="New Session", min_length=1, max_length=255)


class WorksheetSessionPatchRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sort_order: Optional[int] = None


class WorksheetBlockCreateRequest(BaseModel):
    type: WorksheetBlockType
    prompt: Optional[str] = Field(default=None, max_length=4000)
    points: float = Field(default=1.0, ge=0.0, le=100.0)
    options: Optional[List[str]] = None
    answer: Optional[str] = None
    sampleAnswer: Optional[str] = None
    responseLines: Optional[int] = Field(default=None, ge=1, le=12)
    left: Optional[List[str]] = None
    right: Optional[List[str]] = None


class WorksheetBlockPatchRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, max_length=4000)
    points: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    options: Optional[List[str]] = None
    answer: Optional[str] = None
    sampleAnswer: Optional[str] = None
    responseLines: Optional[int] = Field(default=None, ge=1, le=12)
    left: Optional[List[str]] = None
    right: Optional[List[str]] = None


class SessionReorderItem(BaseModel):
    id: str
    sort_order: int = Field(ge=0)


class SessionsReorderRequest(BaseModel):
    order: List[SessionReorderItem] = Field(min_length=1)


class BlockReorderItem(BaseModel):
    id: str
    sort_order: int = Field(ge=0)


class BlocksReorderRequest(BaseModel):
    order: List[BlockReorderItem] = Field(min_length=1)


class DuplicateResponse(BaseModel):
    ok: bool = True
    id: str
