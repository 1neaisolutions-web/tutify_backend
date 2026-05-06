"""
Pydantic schemas for Teacher Tools quiz APIs.

Design goal: response fields can map 1:1 to the existing frontend DemoQuiz shape
without requiring UI changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, RootModel, field_validator


QuizStatus = Literal["draft", "published", "scheduled", "archived"]
QuestionType = Literal["mcq", "tf", "short"]
DifficultyId = Literal["foundation", "standard", "challenge"]


class QuizQuestionStub(BaseModel):
    id: str
    type: QuestionType
    prompt: str
    points: Optional[float] = None
    options: Optional[List[str]] = None
    responseLines: Optional[int] = Field(default=None, alias="response_lines")
    reviewBadges: Optional[Dict[str, Optional[str]]] = None

    @field_validator("options")
    @classmethod
    def _options_non_empty(cls, v: Optional[List[str]]):
        if v is None:
            return v
        cleaned = [x.strip() for x in v if isinstance(x, str) and x.strip()]
        return cleaned


class HandoutLayoutOpts(RootModel[Dict[str, Any]]):
    """Flexible handout layout options stored as an arbitrary object."""


class QuizCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=120)
    grade: str = Field(min_length=1, max_length=80)
    classes: List[str] = Field(default_factory=list)

    timeLimitMinutes: int = Field(default=30, ge=1, le=240)
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None

    status: QuizStatus = "draft"
    assignedAt: Optional[datetime] = None
    dueAt: Optional[datetime] = None

    # Scope
    sourceBookIds: List[str] = Field(default_factory=list)
    scopeTopics: List[str] = Field(default_factory=list)
    scopeRefinement: Optional[str] = None
    generateWithoutSources: bool = False

    difficulty: Optional[DifficultyId] = None
    shuffleQuestions: bool = True
    shuffleAnswers: bool = True
    negativeMarking: bool = False
    handoutLayout: Optional[Dict[str, Any]] = None


class QuizPatchRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    subject: Optional[str] = Field(default=None, min_length=1, max_length=120)
    grade: Optional[str] = Field(default=None, min_length=1, max_length=80)
    classes: Optional[List[str]] = None

    timeLimitMinutes: Optional[int] = Field(default=None, ge=1, le=240)
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None

    status: Optional[QuizStatus] = None
    assignedAt: Optional[datetime] = None
    dueAt: Optional[datetime] = None

    sourceBookIds: Optional[List[str]] = None
    scopeTopics: Optional[List[str]] = None
    scopeRefinement: Optional[str] = None
    generateWithoutSources: Optional[bool] = None

    difficulty: Optional[DifficultyId] = None
    shuffleQuestions: Optional[bool] = None
    shuffleAnswers: Optional[bool] = None
    negativeMarking: Optional[bool] = None
    handoutLayout: Optional[Dict[str, Any]] = None


class QuizGenerateRequest(BaseModel):
    questionCount: int = Field(default=10, ge=1, le=50)
    mixMode: Literal["balanced", "custom"] = "balanced"
    includeMcq: bool = True
    includeTf: bool = True
    includeShort: bool = True
    countsByType: Optional[Dict[str, int]] = None  # {mcq, tf, short} when custom
    difficulty: Optional[DifficultyId] = None
    teacherNotes: Optional[str] = None


class QuizResponse(BaseModel):
    id: str
    title: str
    subject: str
    grade: str
    classes: List[str]

    questions: int
    totalMarks: float
    timeLimitMinutes: int

    status: QuizStatus
    assignedAt: Optional[datetime] = None
    dueAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    submissionCount: int
    avgScore: float

    topic: str
    sourceBookIds: List[str] = Field(default_factory=list)
    scopeTopics: List[str] = Field(default_factory=list)
    scopeRefinement: Optional[str] = None
    sourceSummary: Optional[str] = None

    questionStubs: List[QuizQuestionStub] = Field(default_factory=list)

    studentInstructions: Optional[str] = None
    difficulty: Optional[str] = None
    shuffleQuestions: Optional[bool] = None
    shuffleAnswers: Optional[bool] = None
    negativeMarking: Optional[bool] = None
    handoutLayout: Optional[Dict[str, Any]] = None


class QuizListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[QuizResponse]


class DuplicateResponse(BaseModel):
    ok: bool = True
    id: str


class GenerateResponse(BaseModel):
    ok: bool = True
    generation_run_id: str
    warnings: List[str] = Field(default_factory=list)
    quiz: QuizResponse


class QuizQuestionCreateRequest(BaseModel):
    """Used by POST /quizzes/{id}/questions (add question manually)."""

    type: QuestionType
    prompt: str = Field(min_length=1, max_length=4000)
    points: float = Field(default=1.0, ge=0.0, le=100.0)
    options: Optional[List[str]] = None  # MCQ: 2–6 items
    response_lines: Optional[int] = Field(default=None, ge=1, le=12)  # short only
    reviewBadges: Optional[Dict[str, Optional[str]]] = None

    @field_validator("options")
    @classmethod
    def _clean_options(cls, v):
        if v is None:
            return v
        cleaned = [x.strip() for x in v if isinstance(x, str) and x.strip()]
        return cleaned or None


class QuizQuestionPatchRequest(BaseModel):
    """Used by PATCH /quizzes/{id}/questions/{qid} (edit one question)."""

    prompt: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    points: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    options: Optional[List[str]] = None
    response_lines: Optional[int] = Field(default=None, ge=1, le=12)
    reviewBadges: Optional[Dict[str, Optional[str]]] = None

    @field_validator("options")
    @classmethod
    def _clean_options(cls, v):
        if v is None:
            return v
        cleaned = [x.strip() for x in v if isinstance(x, str) and x.strip()]
        return cleaned or None


class QuestionOrderItem(BaseModel):
    id: str  # UUID as string
    sort_order: int = Field(ge=0)


class QuizQuestionsReorderRequest(BaseModel):
    """Used by PATCH /quizzes/{id}/questions/reorder."""

    order: List[QuestionOrderItem] = Field(min_length=1)


class QuizQuestionResponse(BaseModel):
    """Single question response (also embedded in QuizResponse.questionStubs)."""

    id: str
    type: QuestionType
    prompt: str
    points: float
    options: Optional[List[str]] = None
    responseLines: Optional[int] = None
    reviewBadges: Optional[Dict[str, Optional[str]]] = None

