"""Admin domain models."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ComplianceExportStatus(str, enum.Enum):
    """Status for internal compliance export request tracking."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ComplianceExportRequest(Base):
    """Internal tracking queue for compliance/data export requests (not full DSR workflow)."""

    __tablename__ = "compliance_export_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    requester_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    subject_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)

    request_type = Column(String(50), nullable=False, default="data_export")
    status = Column(
        SQLEnum(ComplianceExportStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ComplianceExportStatus.PENDING,
        index=True,
    )
    reason = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    request_metadata = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    requester = relationship("User", foreign_keys=[requester_user_id])
    subject = relationship("User", foreign_keys=[subject_user_id])
    organization = relationship("Tenant", foreign_keys=[organization_id])

    __table_args__ = (
        Index("idx_compliance_export_status_created", "status", "created_at"),
    )
