"""Models for recommendation analytics performance snapshots."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Date, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class RecommendationPerformanceSnapshot(Base):
    """Daily performance snapshot for recommendations per content and source."""

    __tablename__ = "recommendation_performance_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    content_id = Column(String(150), nullable=False, index=True)
    content_type = Column(String(50), nullable=True)
    recommendation_source = Column(String(100), nullable=True, index=True)

    impressions = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    starts = Column(Integer, nullable=False, default=0)
    completions = Column(Integer, nullable=False, default=0)
    dismissals = Column(Integer, nullable=False, default=0)

    ctr = Column(Float, nullable=True)
    start_rate = Column(Float, nullable=True)
    completion_rate = Column(Float, nullable=True)
    dismissal_rate = Column(Float, nullable=True)

    snapshot_date = Column(Date, nullable=False, index=True)

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
            "idx_recommendation_perf_content_source_date",
            "content_id",
            "recommendation_source",
            "snapshot_date",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RecommendationPerformanceSnapshot(content_id={self.content_id}, "
            f"source={self.recommendation_source}, date={self.snapshot_date})>"
        )

