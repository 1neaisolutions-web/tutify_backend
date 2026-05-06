"""
Database models for persisted YouTube quiz generations.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class YoutubeQuizGeneration(Base):
    __tablename__ = "youtube_quiz_generations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Request fields (stored for regenerate / audit)
    video_url = Column(Text, nullable=False)
    grade_band = Column(String(80), nullable=False)
    subject_lens = Column(String(120), nullable=False)
    learning_focus = Column(String(120), nullable=False)
    quiz_language = Column(String(40), nullable=False, default="English")
    question_styles = Column(JSONB, nullable=False, default=list)  # list[str]
    question_count = Column(Integer, nullable=False)
    lesson_strategy_id = Column(String(64), nullable=True)
    difficulty_level = Column(String(32), nullable=True)
    accessibility_mode = Column(Boolean, nullable=False, default=False)
    video_id = Column(String(32), nullable=True)

    # Display fields
    title = Column(String(500), nullable=False)

    # Response payload (full JSON blob)
    result_json = Column(JSONB, nullable=False)

    # Usage tracking (future-proofing for history ordering)
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_youtube_quiz_user_created_at", "user_id", "created_at"),
    )

