"""Schemas for recommendation analytics."""
from datetime import date as Date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RecommendationPerformanceSnapshotResponse(BaseModel):
    content_id: str
    content_type: Optional[str] = None
    recommendation_source: Optional[str] = None
    impressions: int
    clicks: int
    starts: int
    completions: int
    dismissals: int
    ctr: Optional[float] = None
    start_rate: Optional[float] = None
    completion_rate: Optional[float] = None
    dismissal_rate: Optional[float] = None
    snapshot_date: Date

    model_config = ConfigDict(from_attributes=True)


class RecommendationPerformanceSummary(BaseModel):
    content_id: str
    impressions: int = 0
    clicks: int = 0
    starts: int = 0
    completions: int = 0
    dismissals: int = 0
    ctr: float = 0.0
    completion_rate: float = 0.0


class AggregateRequest(BaseModel):
    # Avoid clashing field name (`date`) with the imported type name.
    date: Date = Field(..., description="Date to aggregate (YYYY-MM-DD)")

