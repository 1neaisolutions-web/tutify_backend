"""
Schemas for the cross-domain user history aggregation endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


SourceType = Literal[
    "quiz",
    "assignment",
    "worksheet",
    "exam",
    "chatbot_conversation",
    "pixgen_generation",
    "youtube_quiz",
    "template_execution",
]


class HistoryItemResponse(BaseModel):
    id: str
    source_type: SourceType
    title: str
    subject: str | None = None
    grade: str | None = None
    status: str | None = None
    pinned: bool = False
    performance_hint: Literal["effective", "needs_improvement"] | None = None
    usage_count: int = 0
    last_used_at: str | None = None
    created_at: datetime
    updated_at: datetime
    meta: dict[str, Any] = {}


class HistoryListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[HistoryItemResponse]


class HistoryStatsResponse(BaseModel):
    total: int
    this_week: int
    pinned: int
    by_source_type: dict[str, int]


class QuotaUsage(BaseModel):
    source_type: str
    used: int
    limit: int
    warning_level: str  # ok | warning | full


class HistoryQuotaResponse(BaseModel):
    tier: str
    per_type_limit: int
    total_limit: int
    total_used: int
    usage: list[QuotaUsage]


class PinToggleRequest(BaseModel):
    source_type: SourceType
    source_id: str
    pinned: bool


class PinToggleResponse(BaseModel):
    source_type: SourceType
    source_id: str
    pinned: bool


class FeedbackUpsertRequest(BaseModel):
    source_type: SourceType
    source_id: str
    hint: Literal["effective", "needs_improvement"]
    note: str | None = None


class FeedbackResponse(BaseModel):
    source_type: SourceType
    source_id: str
    hint: str
    note: str | None = None
    updated_at: str


class ClearHistoryRequest(BaseModel):
    """Same filters as GET /history plus bulk-delete option."""

    source_types: list[SourceType] | None = None
    q: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    keep_pinned: bool = True


class ClearHistoryResponse(BaseModel):
    deleted_count: int

