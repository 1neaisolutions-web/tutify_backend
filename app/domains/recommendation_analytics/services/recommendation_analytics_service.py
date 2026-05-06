"""Aggregation service for recommendation performance snapshots."""
from datetime import date, datetime, timezone
from typing import Dict, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.learning_progress.models import RecommendationEvent
from app.domains.recommendation_analytics.models import RecommendationPerformanceSnapshot

logger = get_logger(__name__)


class RecommendationAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def aggregate_daily_metrics(self, target_date: date) -> None:
        """
        Aggregate recommendation_events into daily performance snapshots.

        Group by content_id + recommendation_source; compute counts and derived metrics.
        """
        start_dt = datetime.combine(target_date, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.combine(target_date, datetime.max.time()).replace(
            tzinfo=timezone.utc
        )

        logger.info("Aggregating recommendation metrics for date=%s", target_date.isoformat())

        # Query raw counts grouped by content_id, source, content_type, event_type
        rows = (
            self.db.query(
                RecommendationEvent.content_id,
                RecommendationEvent.recommendation_source,
                RecommendationEvent.content_type,
                RecommendationEvent.event_type,
                func.count().label("cnt"),
            )
            .filter(
                and_(
                    RecommendationEvent.created_at >= start_dt,
                    RecommendationEvent.created_at <= end_dt,
                )
            )
            .group_by(
                RecommendationEvent.content_id,
                RecommendationEvent.recommendation_source,
                RecommendationEvent.content_type,
                RecommendationEvent.event_type,
            )
            .all()
        )

        # Aggregate per (content_id, source, content_type)
        grouped: Dict[Tuple[str, str | None, str | None], Dict[str, int]] = {}
        for r in rows:
            key = (r.content_id, r.recommendation_source, r.content_type)
            bucket = grouped.setdefault(
                key,
                {
                    "impressions": 0,
                    "clicks": 0,
                    "starts": 0,
                    "completions": 0,
                    "dismissals": 0,
                },
            )
            if r.event_type == "shown":
                bucket["impressions"] += r.cnt
            elif r.event_type == "clicked":
                bucket["clicks"] += r.cnt
            elif r.event_type == "started_learning":
                bucket["starts"] += r.cnt
            elif r.event_type == "completed_learning":
                bucket["completions"] += r.cnt
            elif r.event_type == "dismissed":
                bucket["dismissals"] += r.cnt

        # Upsert snapshots
        for (content_id, source, content_type), counts in grouped.items():
            impressions = counts["impressions"]
            clicks = counts["clicks"]
            starts = counts["starts"]
            completions = counts["completions"]
            dismissals = counts["dismissals"]

            ctr = float(clicks) / impressions if impressions > 0 else None
            start_rate = float(starts) / clicks if clicks > 0 else None
            completion_rate = float(completions) / starts if starts > 0 else None
            dismissal_rate = float(dismissals) / impressions if impressions > 0 else None

            snapshot = (
                self.db.query(RecommendationPerformanceSnapshot)
                .filter(
                    RecommendationPerformanceSnapshot.content_id == content_id,
                    RecommendationPerformanceSnapshot.recommendation_source == source,
                    RecommendationPerformanceSnapshot.snapshot_date == target_date,
                )
                .first()
            )
            now = datetime.now(timezone.utc)
            if snapshot:
                snapshot.content_type = content_type
                snapshot.impressions = impressions
                snapshot.clicks = clicks
                snapshot.starts = starts
                snapshot.completions = completions
                snapshot.dismissals = dismissals
                snapshot.ctr = ctr
                snapshot.start_rate = start_rate
                snapshot.completion_rate = completion_rate
                snapshot.dismissal_rate = dismissal_rate
                snapshot.updated_at = now
            else:
                snapshot = RecommendationPerformanceSnapshot(
                    content_id=content_id,
                    content_type=content_type,
                    recommendation_source=source,
                    impressions=impressions,
                    clicks=clicks,
                    starts=starts,
                    completions=completions,
                    dismissals=dismissals,
                    ctr=ctr,
                    start_rate=start_rate,
                    completion_rate=completion_rate,
                    dismissal_rate=dismissal_rate,
                    snapshot_date=target_date,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(snapshot)

        self.db.commit()

