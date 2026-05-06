"""Query service for recommendation performance summaries."""
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.recommendation_analytics.models import RecommendationPerformanceSnapshot
from app.domains.recommendation_analytics.schemas import RecommendationPerformanceSummary


class RecommendationSummaryService:
    def __init__(self, db: Session):
        self.db = db

    def get_content_performance(self, content_id: str) -> RecommendationPerformanceSummary:
        q = self.db.query(
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.impressions), 0).label(
                "impressions"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.clicks), 0).label(
                "clicks"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.starts), 0).label(
                "starts"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.completions), 0).label(
                "completions"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.dismissals), 0).label(
                "dismissals"
            ),
        ).filter(RecommendationPerformanceSnapshot.content_id == content_id)

        row = q.one()
        impressions = int(row.impressions or 0)
        clicks = int(row.clicks or 0)
        starts = int(row.starts or 0)
        completions = int(row.completions or 0)
        dismissals = int(row.dismissals or 0)

        ctr = float(clicks) / impressions if impressions > 0 else 0.0
        completion_rate = float(completions) / starts if starts > 0 else 0.0

        return RecommendationPerformanceSummary(
            content_id=content_id,
            impressions=impressions,
            clicks=clicks,
            starts=starts,
            completions=completions,
            dismissals=dismissals,
            ctr=ctr,
            completion_rate=completion_rate,
        )

    def _order_for_performance(self, desc: bool, limit: int) -> List[RecommendationPerformanceSnapshot]:
        order = [
            RecommendationPerformanceSnapshot.completion_rate.desc()
            if desc
            else RecommendationPerformanceSnapshot.completion_rate.asc(),
            RecommendationPerformanceSnapshot.ctr.desc()
            if desc
            else RecommendationPerformanceSnapshot.ctr.asc(),
        ]
        return (
            self.db.query(RecommendationPerformanceSnapshot)
            .order_by(*order)
            .limit(limit)
            .all()
        )

    def get_top_performing_content(
        self, limit: int = 20
    ) -> List[RecommendationPerformanceSnapshot]:
        return self._order_for_performance(desc=True, limit=limit)

    def get_low_performing_content(
        self, limit: int = 20
    ) -> List[RecommendationPerformanceSnapshot]:
        return self._order_for_performance(desc=False, limit=limit)

    def get_recommendation_source_performance(
        self, source: str
    ) -> RecommendationPerformanceSummary:
        q = self.db.query(
            RecommendationPerformanceSnapshot.content_id,
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.impressions), 0).label(
                "impressions"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.clicks), 0).label(
                "clicks"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.starts), 0).label(
                "starts"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.completions), 0).label(
                "completions"
            ),
            func.coalesce(func.sum(RecommendationPerformanceSnapshot.dismissals), 0).label(
                "dismissals"
            ),
        ).filter(RecommendationPerformanceSnapshot.recommendation_source == source)

        row = q.one()
        impressions = int(row.impressions or 0)
        clicks = int(row.clicks or 0)
        starts = int(row.starts or 0)
        completions = int(row.completions or 0)
        dismissals = int(row.dismissals or 0)

        ctr = float(clicks) / impressions if impressions > 0 else 0.0
        completion_rate = float(completions) / starts if starts > 0 else 0.0

        return RecommendationPerformanceSummary(
            content_id="*",
            impressions=impressions,
            clicks=clicks,
            starts=starts,
            completions=completions,
            dismissals=dismissals,
            ctr=ctr,
            completion_rate=completion_rate,
        )

