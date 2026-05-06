"""Service for aggregating learning progress metrics."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.learning_progress.enums import LearningSessionStatus
from app.domains.learning_progress.models import LearningSession
from app.domains.learning_progress.schemas import (
    ContentProgressSummary,
    LearningProgressOverview,
)


class ProgressAggregationService:
    def __init__(self, db: Session):
        self.db = db

    def get_progress_overview(self, teacher_id: UUID) -> LearningProgressOverview:
        q = self.db.query(LearningSession).filter(
            LearningSession.teacher_id == teacher_id
        )

        total_sessions = q.count()

        completed_content = (
            self.db.query(LearningSession.content_id)
            .filter(
                LearningSession.teacher_id == teacher_id,
                LearningSession.session_status == LearningSessionStatus.COMPLETED.value,
            )
            .distinct()
            .count()
        )

        in_progress_content = (
            self.db.query(LearningSession.content_id)
            .filter(
                LearningSession.teacher_id == teacher_id,
                LearningSession.session_status.in_(
                    [
                        LearningSessionStatus.STARTED.value,
                        LearningSessionStatus.IN_PROGRESS.value,
                    ]
                ),
            )
            .distinct()
            .count()
        )

        total_seconds = (
            self.db.query(func.coalesce(func.sum(LearningSession.duration_seconds), 0))
            .filter(LearningSession.teacher_id == teacher_id)
            .scalar()
        )
        total_minutes = int(total_seconds // 60)

        last_activity: Optional[datetime] = (
            self.db.query(func.max(LearningSession.last_event_at))
            .filter(LearningSession.teacher_id == teacher_id)
            .scalar()
        )

        return LearningProgressOverview(
            total_sessions=total_sessions,
            completed_content_count=completed_content,
            in_progress_content_count=in_progress_content,
            total_learning_minutes=total_minutes,
            last_activity_at=last_activity,
        )

    def get_content_progress(
        self, teacher_id: UUID, content_id: str
    ) -> ContentProgressSummary:
        q = self.db.query(LearningSession).filter(
            LearningSession.teacher_id == teacher_id,
            LearningSession.content_id == content_id,
        )
        total_sessions = q.count()
        completed_sessions = q.filter(
            LearningSession.session_status == LearningSessionStatus.COMPLETED.value
        ).count()
        in_progress_sessions = q.filter(
            LearningSession.session_status.in_(
                [
                    LearningSessionStatus.STARTED.value,
                    LearningSessionStatus.IN_PROGRESS.value,
                ]
            )
        ).count()

        total_seconds = (
            self.db.query(func.coalesce(func.sum(LearningSession.duration_seconds), 0))
            .filter(
                LearningSession.teacher_id == teacher_id,
                LearningSession.content_id == content_id,
            )
            .scalar()
        )
        total_minutes = int(total_seconds // 60)

        last_activity: Optional[datetime] = (
            self.db.query(func.max(LearningSession.last_event_at))
            .filter(
                LearningSession.teacher_id == teacher_id,
                LearningSession.content_id == content_id,
            )
            .scalar()
        )

        # Latest progress across sessions for this content
        latest_progress = (
            self.db.query(LearningSession.progress_percent)
            .filter(
                LearningSession.teacher_id == teacher_id,
                LearningSession.content_id == content_id,
            )
            .order_by(LearningSession.updated_at.desc())
            .limit(1)
            .scalar()
        )

        return ContentProgressSummary(
            content_id=content_id,
            total_sessions=total_sessions,
            completed_sessions=completed_sessions,
            in_progress_sessions=in_progress_sessions,
            total_learning_minutes=total_minutes,
            last_activity_at=last_activity,
            progress_percent=float(latest_progress or 0.0),
        )

