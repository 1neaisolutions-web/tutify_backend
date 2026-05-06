"""
Teacher Intelligence domain models.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class TeacherFeatureSnapshot(Base):
    """ML-ready feature snapshot derived from CTP."""

    __tablename__ = "teacher_feature_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    teacher_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    feature_schema_version = Column(String(50), nullable=False, index=True)
    source_hash = Column(String(128), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False)

    features = Column(JSONB, nullable=False)

    is_latest = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[teacher_id])
    ml_outputs = relationship("MLOutput", back_populates="feature_snapshot", foreign_keys="MLOutput.feature_snapshot_id")
    pipeline_runs = relationship(
        "PipelineRun", back_populates="feature_snapshot", foreign_keys="PipelineRun.feature_snapshot_id"
    )

    __table_args__ = (
        Index("idx_teacher_feature_snapshot_teacher_latest", "teacher_id", "is_latest"),
    )

    def __repr__(self) -> str:
        return f"<TeacherFeatureSnapshot(id={self.id}, teacher_id={self.teacher_id}, is_latest={self.is_latest})>"


class MLOutput(Base):
    """Stored output from an ML pipeline run."""

    __tablename__ = "ml_outputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    teacher_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    pipeline_name = Column(String(100), nullable=False, index=True)
    pipeline_version = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=False)

    feature_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_feature_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    generated_at = Column(DateTime(timezone=True), nullable=False)

    results = Column(JSONB, nullable=False)
    confidence_score = Column(Float, nullable=True)
    is_latest = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[teacher_id])
    feature_snapshot = relationship(
        "TeacherFeatureSnapshot", back_populates="ml_outputs", foreign_keys=[feature_snapshot_id]
    )

    __table_args__ = (
        Index("idx_ml_outputs_teacher_latest", "teacher_id", "is_latest"),
        Index("idx_ml_outputs_teacher_pipeline", "teacher_id", "pipeline_name"),
    )

    def __repr__(self) -> str:
        return f"<MLOutput(id={self.id}, teacher_id={self.teacher_id}, pipeline={self.pipeline_name})>"


class PipelineRun(Base):
    """Tracking record for an ML pipeline execution."""

    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    teacher_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    pipeline_name = Column(String(100), nullable=False, index=True)
    pipeline_version = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=False)

    feature_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_feature_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status = Column(String(50), nullable=False, index=True)

    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    runtime_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[teacher_id])
    feature_snapshot = relationship(
        "TeacherFeatureSnapshot", back_populates="pipeline_runs", foreign_keys=[feature_snapshot_id]
    )

    __table_args__ = (Index("idx_pipeline_runs_teacher_status", "teacher_id", "status"),)

    def __repr__(self) -> str:
        return f"<PipelineRun(id={self.id}, teacher_id={self.teacher_id}, status={self.status})>"
