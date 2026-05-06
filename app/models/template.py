"""
Template model for system templates.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Text, Boolean, JSON, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.base_class import Base


class TemplateCategory(str, enum.Enum):
    """Template category enumeration."""
    LESSON_DESIGN = "lesson_design"
    ASSESSMENT = "assessment"
    BEHAVIOR = "behavior"
    SUBJECT_SPECIFIC = "subject_specific"
    COMMUNICATION = "communication"


class Template(Base):
    """Template model representing a system template."""

    __tablename__ = "templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(SQLEnum(TemplateCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    subject_default = Column(String(50), nullable=True)
    grade_bands_supported = Column(JSON, nullable=True)  # Array of grade bands
    stub_config = Column(JSON, nullable=True)  # Template-specific stub output configuration
    is_system_template = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Template(id={self.id}, slug={self.slug}, name={self.name})>"

