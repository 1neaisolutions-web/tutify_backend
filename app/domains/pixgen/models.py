"""
PixGen domain models.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class PixGenGeneration(Base):
    """Stores generated media metadata for PixGen image requests."""

    __tablename__ = "pixgen_generations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    style_preset = Column(String(120), nullable=False)
    aspect_ratio = Column(String(50), nullable=False)
    image_url = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="queued", index=True)
    provider = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    error = Column(Text, nullable=True)
    generation_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_pixgen_user_created_at", "user_id", "created_at"),
        Index("idx_pixgen_status_created_at", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PixGenGeneration(id={self.id}, user_id={self.user_id}, status={self.status})>"
