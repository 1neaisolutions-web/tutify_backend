"""Service for managing learning sessions."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.learning_progress.enums import LearningSessionStatus
from app.domains.learning_progress.models import LearningSession
from app.domains.learning_progress.schemas import LearningSessionCreate, LearningSessionUpdate

logger = get_logger(__name__)


def _merge_session_metadata(
    existing: Optional[dict],
    incoming: Optional[dict],
) -> dict:
    """Shallow merge; deep-merge tutorial_progress so step patches don't wipe fields."""
    if not incoming:
        return dict(existing or {})
    base = dict(existing or {})
    for key, value in incoming.items():
        if (
            key == "tutorial_progress"
            and isinstance(base.get(key), dict)
            and isinstance(value, dict)
        ):
            merged_tp = {**(base.get(key) or {}), **value}
            base[key] = merged_tp
        else:
            base[key] = value
    return base


class LearningSessionService:
    def __init__(self, db: Session):
        self.db = db

    def start_session(self, teacher_id: UUID, data: LearningSessionCreate) -> LearningSession:
        """Start or reuse an active session for teacher + content."""
        # Try to reuse an existing in-progress session
        existing = (
            self.db.query(LearningSession)
            .filter(
                LearningSession.teacher_id == teacher_id,
                LearningSession.content_id == data.content_id,
                LearningSession.session_status.in_(
                    [LearningSessionStatus.STARTED.value, LearningSessionStatus.IN_PROGRESS.value]
                ),
            )
            .order_by(LearningSession.started_at.desc())
            .first()
        )
        if existing:
            logger.info(
                "Reusing existing learning session id=%s for teacher_id=%s content_id=%s",
                existing.id,
                teacher_id,
                data.content_id,
            )
            return existing

        now = datetime.now(timezone.utc)
        session = LearningSession(
            teacher_id=teacher_id,
            content_id=data.content_id,
            content_type=data.content_type,
            session_status=LearningSessionStatus.STARTED.value,
            started_at=now,
            completed_at=None,
            progress_percent=0.0,
            duration_seconds=0,
            last_event_at=None,
            locale=data.locale,
            session_metadata=data.session_metadata or {},
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        logger.info(
            "Started new learning session id=%s for teacher_id=%s content_id=%s",
            session.id,
            teacher_id,
            data.content_id,
        )
        return session

    def get_session(self, session_id: UUID, teacher_id: UUID) -> Optional[LearningSession]:
        return (
            self.db.query(LearningSession)
            .filter(LearningSession.id == session_id, LearningSession.teacher_id == teacher_id)
            .first()
        )

    def list_sessions(
        self,
        teacher_id: UUID,
        content_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[LearningSession]:
        q = self.db.query(LearningSession).filter(LearningSession.teacher_id == teacher_id)
        if content_id:
            q = q.filter(LearningSession.content_id == content_id)
        if status:
            q = q.filter(LearningSession.session_status == status)
        return (
            q.order_by(LearningSession.started_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update_session(
        self, session_id: UUID, teacher_id: UUID, data: LearningSessionUpdate
    ) -> Optional[LearningSession]:
        session = self.get_session(session_id, teacher_id)
        if not session:
            return None
        update = data.model_dump(exclude_unset=True)
        if "session_metadata" in update and update["session_metadata"] is not None:
            session.session_metadata = _merge_session_metadata(
                session.session_metadata, update["session_metadata"]
            )
        if "progress_percent" in update and update["progress_percent"] is not None:
            session.progress_percent = float(update["progress_percent"])
        if "duration_seconds" in update and update["duration_seconds"] is not None:
            session.duration_seconds = int(update["duration_seconds"])
        if "session_status" in update and update["session_status"] is not None:
            session.session_status = update["session_status"]
        session.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(session)
        return session

    def complete_session(
        self, session_id: UUID, teacher_id: UUID, progress_percent: float = 100.0
    ) -> Optional[LearningSession]:
        session = self.get_session(session_id, teacher_id)
        if not session:
            return None
        session.session_status = LearningSessionStatus.COMPLETED.value
        session.progress_percent = max(session.progress_percent, progress_percent)
        session.completed_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_active_session_for_content(
        self, teacher_id: UUID, content_id: str
    ) -> Optional[LearningSession]:
        return (
            self.db.query(LearningSession)
            .filter(
                LearningSession.teacher_id == teacher_id,
                LearningSession.content_id == content_id,
                LearningSession.session_status.in_(
                    [LearningSessionStatus.STARTED.value, LearningSessionStatus.IN_PROGRESS.value]
                ),
            )
            .order_by(LearningSession.started_at.desc())
            .first()
        )

