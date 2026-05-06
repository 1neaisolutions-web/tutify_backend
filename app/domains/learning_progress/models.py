"""SQLAlchemy models for learning progress and engagement analytics."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base_class import Base


class LearningSession(Base):
    """A learning session for a teacher on a specific content item."""

    __tablename__ = "learning_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id = Column(String(150), nullable=False, index=True)
    content_type = Column(String(50), nullable=False, index=True)
    session_status = Column(String(50), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    progress_percent = Column(Float, nullable=False, default=0.0)
    duration_seconds = Column(Integer, nullable=False, default=0)
    last_event_at = Column(DateTime(timezone=True), nullable=True)
    locale = Column(String(20), nullable=True)
    session_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_learning_sessions_teacher_content_status",
            "teacher_id",
            "content_id",
            "session_status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LearningSession(id={self.id}, teacher_id={self.teacher_id}, "
            f"content_id={self.content_id}, status={self.session_status})>"
        )


class LearningEvent(Base):
    """Append-only learning events within sessions."""

    __tablename__ = "learning_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("learning_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id = Column(String(150), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<LearningEvent(id={self.id}, session_id={self.session_id}, "
            f"event_type={self.event_type})>"
        )


class RecommendationEvent(Base):
    """Events capturing recommendation interactions."""

    __tablename__ = "recommendation_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id = Column(String(150), nullable=False, index=True)
    content_type = Column(String(50), nullable=True)
    recommendation_source = Column(String(100), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<RecommendationEvent(id={self.id}, teacher_id={self.teacher_id}, "
            f"content_id={self.content_id}, event_type={self.event_type})>"
        )


class ContentFeedback(Base):
    """Teacher feedback on content items."""

    __tablename__ = "content_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id = Column(String(150), nullable=False, index=True)
    rating = Column(Integer, nullable=True)
    difficulty_feedback = Column(String(50), nullable=True)
    usefulness_feedback = Column(String(50), nullable=True)
    comment = Column(Text, nullable=True)
    feedback_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ContentFeedback(id={self.id}, teacher_id={self.teacher_id}, "
            f"content_id={self.content_id})>"
        )

