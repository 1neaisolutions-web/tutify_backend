"""Recommendation Analytics API routes."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user, require_any_role
from app.domains.auth.models import User
from app.domains.recommendation_analytics import schemas as ra_schemas
from app.domains.recommendation_analytics.services import (
    RecommendationAnalyticsService,
    RecommendationSummaryService,
)

router = APIRouter(
    prefix="/api/v1/recommendation-analytics", tags=["recommendation-analytics"]
)


@router.get(
    "/content/{content_id}",
    response_model=ra_schemas.RecommendationPerformanceSummary,
)
def get_content_performance(
    content_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get aggregate performance summary for a specific content_id."""
    service = RecommendationSummaryService(db)
    summary = service.get_content_performance(content_id)
    return summary


@router.get(
    "/top-performing",
    response_model=List[ra_schemas.RecommendationPerformanceSnapshotResponse],
)
def get_top_performing(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get top performing content by completion_rate then ctr."""
    service = RecommendationSummaryService(db)
    limit_val = max(1, min(limit, 100))
    snapshots = service.get_top_performing_content(limit=limit_val)
    return snapshots


@router.get(
    "/low-performing",
    response_model=List[ra_schemas.RecommendationPerformanceSnapshotResponse],
)
def get_low_performing(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get low performing content by completion_rate then ctr."""
    service = RecommendationSummaryService(db)
    limit_val = max(1, min(limit, 100))
    snapshots = service.get_low_performing_content(limit=limit_val)
    return snapshots


@router.post(
    "/aggregate",
    response_model=None,
    status_code=status.HTTP_202_ACCEPTED,
)
def aggregate_daily(
    body: ra_schemas.AggregateRequest,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Trigger daily metrics aggregation for the given date (admin only)."""
    service = RecommendationAnalyticsService(db)
    service.aggregate_daily_metrics(body.date)
    return None

