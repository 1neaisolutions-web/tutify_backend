"""
Pydantic schemas for TemplateExecution model (internal use).
"""
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel

from app.models.template_execution import TemplateExecution


class TemplateExecutionBase(BaseModel):
    """Base schema for template execution."""

    template_id: UUID
    template_version_id: Optional[UUID] = None
    template_version: Optional[int] = None
    user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    model_used: Optional[str] = None
    provider_used: Optional[str] = None
    token_usage: Optional[Dict[str, int]] = None
    cost_estimate: Optional[Decimal] = None
    latency_ms: Optional[int] = None
    cache_hit: bool = False
    alignment_flags: Optional[Dict[str, Any]] = None


class TemplateExecutionCreate(TemplateExecutionBase):
    """Schema for creating a template execution."""

    pass


class TemplateExecutionResponse(TemplateExecutionBase):
    """Schema for template execution response (internal)."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TemplateExecutionDetail(TemplateExecutionResponse):
    """Detailed schema for template execution with full information."""

    pass


class TemplateExecutionPublic(BaseModel):
    """Public API response for history restore (owner-scoped GET)."""

    id: UUID
    template_id: UUID
    template_slug: str
    template_version: Optional[int] = None
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    model_used: Optional[str] = None
    provider_used: Optional[str] = None
    created_at: datetime
    updated_at: datetime

