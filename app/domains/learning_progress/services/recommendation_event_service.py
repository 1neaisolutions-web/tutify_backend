"""Service for recording recommendation interaction events."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.learning_progress.models import RecommendationEvent
from app.domains.learning_progress.schemas import RecommendationEventCreate


class RecommendationEventService:
    def __init__(self, db: Session):
        self.db = db

    def record_event(self, teacher_id: UUID, data: RecommendationEventCreate) -> RecommendationEvent:
        event = RecommendationEvent(
            teacher_id=teacher_id,
            content_id=data.content_id,
            content_type=data.content_type,
            recommendation_source=data.recommendation_source,
            event_type=data.event_type,
            event_metadata=data.event_metadata or {},
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_events(
        self,
        teacher_id: UUID,
        content_id: Optional[str] = None,
        event_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[RecommendationEvent]:
        q = self.db.query(RecommendationEvent).filter(
            RecommendationEvent.teacher_id == teacher_id
        )
        if content_id:
            q = q.filter(RecommendationEvent.content_id == content_id)
        if event_type:
            q = q.filter(RecommendationEvent.event_type == event_type)
        return (
            q.order_by(RecommendationEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

