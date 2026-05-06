"""
Pydantic schemas for Teacher Tools exam APIs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

ExamStatus = Literal["draft", "scheduled", "completed", "archived"]
ExamQuestionType = Literal["mcq", "short", "long"]
ExamType = Literal["Unit test", "Mid-term", "Final exam", "Mock exam"]
TermValue = Literal["Term 1", "Term 2", "Term 3"]
InternationalStandard = Literal["Cambridge-style", "IB-aligned", "Standard", "National curriculum"]
DifficultyId = Literal["foundation", "standard", "challenge"]


class ExamPaperConfigSchema(BaseModel):
    objCount: int = Field(default=20, ge=0, le=100)
    objMarksPer: float = Field(default=1.0, ge=0)
    objOptions: Literal[4, 5] = 4
    objNegative: bool = False
    shortCount: int = Field(default=6, ge=0, le=20)
    shortMarksPer: float = Field(default=5.0, ge=0)
    shortRule: Literal["all", "pickNM"] = "pickNM"
    shortN: int = Field(default=4, ge=0)
    shortM: int = Field(default=6, ge=0)
    longCount: int = Field(default=3, ge=0, le=10)
    longMarksPer: float = Field(default=10.0, ge=0)
    longSubparts: int = Field(default=3, ge=1, le=6)
    longRule: Literal["all", "pickNM"] = "pickNM"
    longN: int = Field(default=2, ge=0)
    longM: int = Field(default=3, ge=0)


class ExamSectionResponse(BaseModel):
    id: str
    sortOrder: int
    title: str
    marks: float
    description: Optional[str] = None


class ExamMcqResponse(BaseModel):
    id: str
    sortOrder: int
    stem: str
    options: List[str]
    marksPer: float


class ExamShortResponse(BaseModel):
    id: str
    sortOrder: int
    stem: str
    marksPer: float


class ExamLongResponse(BaseModel):
    id: str
    sortOrder: int
    stem: str
    subparts: List[str]
    marksPer: float


class ExamApiResponse(BaseModel):
    id: str
    title: str
    subject: str
    grade: str
    examType: str
    term: str
    internationalStandard: str
    durationMinutes: int
    totalMarks: float
    scheduleStart: Optional[datetime] = None
    scheduleEnd: Optional[datetime] = None
    classes: List[str]
    status: ExamStatus
    completionPct: float
    sectionTargetCount: int
    sourceBookIds: List[str]
    scopeTopics: List[str]
    scopeRefinement: Optional[str] = None
    sourceSummary: Optional[str] = None
    generateWithoutSources: bool
    paper: ExamPaperConfigSchema
    sections: List[ExamSectionResponse]
    mcqs: List[ExamMcqResponse]
    shorts: List[ExamShortResponse]
    longs: List[ExamLongResponse]
    handoutLayout: Optional[Dict[str, Any]] = None
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class ExamListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ExamApiResponse]


class ExamCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=120)
    grade: str = Field(min_length=1, max_length=80)
    examType: str = Field(default="Unit test", max_length=80)
    term: str = Field(default="Term 1", max_length=40)
    internationalStandard: str = Field(default="Standard", max_length=80)
    durationMinutes: int = Field(default=60, ge=15, le=360)
    scheduleStart: Optional[datetime] = None
    scheduleEnd: Optional[datetime] = None
    classes: List[str] = Field(default_factory=list)
    status: ExamStatus = "draft"
    sectionTargetCount: int = Field(default=4, ge=1, le=12)
    sourceBookIds: List[str] = Field(default_factory=list)
    scopeTopics: List[str] = Field(default_factory=list)
    scopeRefinement: Optional[str] = None
    generateWithoutSources: bool = False
    paper: ExamPaperConfigSchema = Field(default_factory=ExamPaperConfigSchema)
    handoutLayout: Optional[Dict[str, Any]] = None
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None


class ExamPatchRequest(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    examType: Optional[str] = None
    term: Optional[str] = None
    internationalStandard: Optional[str] = None
    durationMinutes: Optional[int] = Field(default=None, ge=15, le=360)
    scheduleStart: Optional[datetime] = None
    scheduleEnd: Optional[datetime] = None
    classes: Optional[List[str]] = None
    status: Optional[ExamStatus] = None
    completionPct: Optional[float] = None
    sectionTargetCount: Optional[int] = Field(default=None, ge=1, le=12)
    sourceBookIds: Optional[List[str]] = None
    scopeTopics: Optional[List[str]] = None
    scopeRefinement: Optional[str] = None
    generateWithoutSources: Optional[bool] = None
    paper: Optional[ExamPaperConfigSchema] = None
    handoutLayout: Optional[Dict[str, Any]] = None
    studentInstructions: Optional[str] = None
    teacherNotes: Optional[str] = None


class ExamGenerateRequest(BaseModel):
    difficulty: Optional[DifficultyId] = None
    teacherNotes: Optional[str] = None
    regenerateScope: Literal["all", "mcq", "short", "long"] = "all"


class ExamGenerateResponse(BaseModel):
    ok: bool = True
    generation_run_id: str
    warnings: List[str] = Field(default_factory=list)
    exam: ExamApiResponse


class DuplicateResponse(BaseModel):
    ok: bool = True
    id: str


class ExamMcqCreateRequest(BaseModel):
    stem: str = Field(min_length=1, max_length=4000)
    options: List[str] = Field(min_length=2, max_length=6)
    marksPer: float = Field(default=1.0, ge=0, le=100)


class ExamMcqPatchRequest(BaseModel):
    stem: Optional[str] = Field(default=None, max_length=4000)
    options: Optional[List[str]] = None
    marksPer: Optional[float] = None


class ExamShortCreateRequest(BaseModel):
    stem: str = Field(min_length=1, max_length=4000)
    marksPer: float = Field(default=5.0, ge=0, le=100)


class ExamShortPatchRequest(BaseModel):
    stem: Optional[str] = None
    marksPer: Optional[float] = None


class ExamLongCreateRequest(BaseModel):
    stem: str = Field(min_length=1, max_length=4000)
    subparts: List[str] = Field(min_length=1, max_length=6)
    marksPer: float = Field(default=10.0, ge=0, le=100)


class ExamLongPatchRequest(BaseModel):
    stem: Optional[str] = None
    subparts: Optional[List[str]] = None
    marksPer: Optional[float] = None


class QuestionReorderItem(BaseModel):
    id: str
    sort_order: int = Field(ge=0)


class ExamQuestionsReorderRequest(BaseModel):
    order: List[QuestionReorderItem] = Field(min_length=1)
