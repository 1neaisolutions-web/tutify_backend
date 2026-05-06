"""
Cross-domain user annotations for history items.

Pins and feedback apply across multiple source tables, so they live in dedicated tables keyed by:
  (user_id, source_type, source_id)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class UserContentPin(Base):
    __tablename__ = "user_content_pins"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_user_content_pin"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(40), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])


class UserContentFeedback(Base):
    __tablename__ = "user_content_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_user_content_feedback"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(40), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)
    hint = Column(String(32), nullable=False)  # effective | needs_improvement
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])

