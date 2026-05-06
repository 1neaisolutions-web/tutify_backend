"""
Content Registry domain models.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base_class import Base


class ContentRegistryItem(Base):
    """Canonical learning content item in the registry."""

    __tablename__ = "content_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    content_id = Column(String(150), unique=True, nullable=False, index=True)
    content_type = Column(String(50), nullable=False, index=True)
    schema_version = Column(String(50), nullable=False)
    content_version_major = Column(Integer, default=1, nullable=False)
    content_version_minor = Column(Integer, default=0, nullable=False)
    content_version_patch = Column(Integer, default=0, nullable=False)
    locale = Column(String(20), default="en", nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    subtitle = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)
    estimated_duration_min = Column(Integer, nullable=True)
    difficulty = Column(String(50), nullable=True, index=True)
    impact_level = Column(String(50), nullable=True)
    tags = Column(JSONB, default=dict, nullable=False)
    alignment = Column(JSONB, default=dict, nullable=False)
    json_blob = Column(JSONB, nullable=True)
    source_type = Column(String(50), nullable=True)
    source_ref = Column(String(255), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_content_registry_type_status_locale",
            "content_type",
            "status",
            "locale",
        ),
    )

    def __repr__(self) -> str:
        return f"<ContentRegistryItem(id={self.id}, content_id={self.content_id}, content_type={self.content_type})>"
