"""
TemplateVersion model for versioned template definitions.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, JSON, Text, DateTime, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.base_class import Base


class TemplateVersionStatus(str, enum.Enum):
    """Template version status enumeration."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class TemplateVersion(Base):
    """
    TemplateVersion model representing a versioned template definition.
    
    IMPORTANT: Once a version is published, it must not be mutated.
    This ensures immutability of published template versions for audit and consistency.
    """

    __tablename__ = "template_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(SQLEnum(TemplateVersionStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TemplateVersionStatus.DRAFT.value)
    input_schema = Column(JSON, nullable=False)  # JSON schema for input validation
    output_schema = Column(JSON, nullable=True)  # JSON schema for output structure
    stub_config = Column(JSON, nullable=True)  # Version-specific stub output configuration
    prompt_definition = Column(JSON, nullable=True)  # Prompt template or definition
    model_config = Column(JSON, nullable=True)  # LLM model configuration
    created_by = Column(UUID(as_uuid=True), nullable=True)  # FK to user (nullable for now)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    template = relationship("Template", backref="versions")

    # Unique constraint: one version number per template
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_version"),
        {"comment": "Template versions. Published versions must not be mutated."},
    )

    def __repr__(self) -> str:
        return f"<TemplateVersion(id={self.id}, template_id={self.template_id}, version={self.version}, status={self.status})>"

