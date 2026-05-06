"""
TemplateExecution model for tracking template executions.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, JSON, Boolean, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class TemplateExecution(Base):
    """TemplateExecution model for tracking template execution history."""

    __tablename__ = "template_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True)
    template_version_id = Column(UUID(as_uuid=True), ForeignKey("template_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    template_version = Column(Integer, nullable=True)  # Version number for quick reference
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # FK to user (nullable for demo)
    tenant_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # FK to tenant (nullable for now)
    input_data = Column(JSON, nullable=False)  # Input data used for execution
    output_data = Column(JSON, nullable=True)  # Output data matching universal output structure
    model_used = Column(String(100), nullable=True)  # LLM model identifier
    provider_used = Column(String(50), nullable=True)  # LLM provider (e.g., "openai", "anthropic")
    token_usage = Column(JSON, nullable=True)  # {prompt: int, completion: int, total: int}
    cost_estimate = Column(Numeric(10, 6), nullable=True)  # Estimated cost in USD
    latency_ms = Column(Integer, nullable=True)  # Execution latency in milliseconds
    cache_hit = Column(Boolean, default=False, nullable=False)  # Whether result was from cache
    alignment_flags = Column(JSON, nullable=True)  # Flags for alignment checks
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<TemplateExecution(id={self.id}, template_id={self.template_id}, created_at={self.created_at})>"

