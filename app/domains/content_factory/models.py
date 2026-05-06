"""
Content Factory domain models.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base_class import Base


class ContentGenerationJob(Base):
    """Tracks an agentic content generation run from request to publish."""

    __tablename__ = "content_generation_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    requested_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    content_type = Column(String(50), nullable=False, index=True)
    # High-level job type for orchestration (e.g. micro_course, ai_guided_tutorial, learning_path)
    job_type = Column(String(50), nullable=False, index=True, default="micro_course")
    generation_strategy = Column(String(50), nullable=False)
    topic = Column(String(255), nullable=False)
    subject = Column(String(100), nullable=True)
    # Target subject/category for gap filling (normalized; may duplicate subject for backwards-compat)
    target_subject = Column(String(100), nullable=True, index=True)
    grade_band = Column(String(50), nullable=True)
    difficulty = Column(String(50), nullable=True)
    locale = Column(String(20), default="en", nullable=False)

    status = Column(String(50), nullable=False, index=True)
    current_step = Column(String(50), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    quality_score = Column(Float, nullable=True)
    result_content_id = Column(String(150), nullable=True)
    error_message = Column(Text, nullable=True)
    # Source of the job (e.g. user_request, gap_detection)
    source = Column(String(50), nullable=True, index=True)

    # Review / approval state
    review_required = Column(Integer, default=0, nullable=False)  # 0 = False, 1 = True (for backward compat)
    publication_policy_decision = Column(String(50), nullable=True)
    approved_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Intermediate outputs per step (curriculum, pedagogy, structure, assessment, review, quality)
    step_outputs = Column(JSONB, default=dict, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ContentGenerationJob(id={self.id}, status={self.status}, "
            f"content_type={self.content_type}, topic={self.topic})>"
        )


class ContentGenerationReview(Base):
    """Human review/approval record for a content generation job."""

    __tablename__ = "content_generation_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision = Column(String(50), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    review_metadata = Column(JSONB, nullable=True)
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
        Index("ix_content_generation_reviews_job_decision", "job_id", "decision"),
    )

    def __repr__(self) -> str:
        return f"<ContentGenerationReview(id={self.id}, job_id={self.job_id}, decision={self.decision})>"
