"""Service for recording and querying learning events."""
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.learning_progress.enums import LearningEventType, LearningSessionStatus
from app.domains.learning_progress.models import LearningEvent, LearningSession
from app.domains.learning_progress.schemas import LearningEventCreate

logger = get_logger(__name__)


class LearningEventService:
    def __init__(self, db: Session):
        self.db = db

    def record_event(self, teacher_id: UUID, data: LearningEventCreate) -> LearningEvent:
        """Record a learning event and update the related session."""
        session = (
            self.db.query(LearningSession)
            .filter(
                LearningSession.id == data.session_id,
                LearningSession.teacher_id == teacher_id,
            )
            .first()
        )
        if not session:
            raise ValueError("Session not found or does not belong to teacher")

        now = datetime.now(timezone.utc)
        event = LearningEvent(
            session_id=session.id,
            teacher_id=teacher_id,
            content_id=data.content_id,
            event_type=data.event_type,
            event_metadata=data.event_metadata or {},
            created_at=now,
        )
        self.db.add(event)

        # Update session aggregate fields
        session.last_event_at = now
        # Mark as in_progress when any event recorded after start
        if session.session_status in (
            LearningSessionStatus.STARTED.value,
            LearningSessionStatus.ABANDONED.value,
        ):
            session.session_status = LearningSessionStatus.IN_PROGRESS.value

        # Simple duration approximation: increment by small fixed amount or use metadata if provided
        if "duration_increment_seconds" in data.event_metadata:
            inc = int(data.event_metadata.get("duration_increment_seconds") or 0)
            session.duration_seconds = max(0, session.duration_seconds + inc)

        # Progress heuristics for some event types
        if data.event_type in (
            LearningEventType.LESSON_COMPLETED.value,
            LearningEventType.STEP_COMPLETED.value,
            LearningEventType.QUIZ_PASSED.value,
        ):
            session.progress_percent = max(session.progress_percent, 50.0)

        if data.event_type == LearningEventType.CONTENT_COMPLETED.value:
            session.progress_percent = 100.0
            session.session_status = LearningSessionStatus.COMPLETED.value
            session.completed_at = now

        session.updated_at = now

        self.db.commit()
        self.db.refresh(event)
        return event

    def list_events_for_session(
        self, session_id: UUID, teacher_id: UUID
    ) -> List[LearningEvent]:
        return (
            self.db.query(LearningEvent)
            .filter(
                LearningEvent.session_id == session_id,
                LearningEvent.teacher_id == teacher_id,
            )
            .order_by(LearningEvent.created_at.asc())
            .all()
        )

