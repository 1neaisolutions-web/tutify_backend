"""
Pydantic schemas for Content Registry domain.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- Content registry item ----------
class ContentRegistryCreate(BaseModel):
    """Create content registry item."""

    content_id: str = Field(..., min_length=1, max_length=150)
    content_type: str = Field(..., min_length=1, max_length=50)
    schema_version: str = Field(..., min_length=1, max_length=50)
    content_version_major: int = 1
    content_version_minor: int = 0
    content_version_patch: int = 0
    locale: str = Field(default="en", max_length=20)
    status: str = Field(default="draft", max_length=50)
    title: str = Field(..., min_length=1, max_length=300)
    subtitle: Optional[str] = Field(None, max_length=500)
    summary: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    estimated_duration_min: Optional[int] = None
    difficulty: Optional[str] = Field(None, max_length=50)
    impact_level: Optional[str] = Field(None, max_length=50)
    tags: Dict[str, Any] = Field(default_factory=dict)
    alignment: Dict[str, Any] = Field(default_factory=dict)
    json_blob: Optional[Dict[str, Any]] = None
    source_type: Optional[str] = Field(None, max_length=50)
    source_ref: Optional[str] = Field(None, max_length=255)


class ContentRegistryUpdate(BaseModel):
    """Update content registry item (partial)."""

    content_type: Optional[str] = Field(None, min_length=1, max_length=50)
    schema_version: Optional[str] = Field(None, min_length=1, max_length=50)
    content_version_major: Optional[int] = None
    content_version_minor: Optional[int] = None
    content_version_patch: Optional[int] = None
    locale: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=50)
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    subtitle: Optional[str] = Field(None, max_length=500)
    summary: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    estimated_duration_min: Optional[int] = None
    difficulty: Optional[str] = Field(None, max_length=50)
    impact_level: Optional[str] = Field(None, max_length=50)
    tags: Optional[Dict[str, Any]] = None
    alignment: Optional[Dict[str, Any]] = None
    json_blob: Optional[Dict[str, Any]] = None
    source_type: Optional[str] = Field(None, max_length=50)
    source_ref: Optional[str] = Field(None, max_length=255)


class ContentRegistryResponse(BaseModel):
    """Full content registry item response."""

    id: UUID
    content_id: str
    content_type: str
    schema_version: str
    content_version_major: int
    content_version_minor: int
    content_version_patch: int
    locale: str
    status: str
    title: str
    subtitle: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = None
    estimated_duration_min: Optional[int] = None
    difficulty: Optional[str] = None
    impact_level: Optional[str] = None
    tags: Dict[str, Any] = Field(default_factory=dict)
    alignment: Dict[str, Any] = Field(default_factory=dict)
    json_blob: Optional[Dict[str, Any]] = None
    source_type: Optional[str] = None
    source_ref: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContentRegistryListItem(BaseModel):
    """List item (subset for listing)."""

    id: UUID
    content_id: str
    content_type: str
    locale: str
    status: str
    title: str
    category: Optional[str] = None
    estimated_duration_min: Optional[int] = None
    difficulty: Optional[str] = None
    source_type: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Recommendation (Learning Hub friendly) ----------
class RecommendationCard(BaseModel):
    """Learning Hub recommendation card backed by content registry."""

    content_id: str
    content_type: str
    title: str
    subtitle: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = None
    estimated_duration_min: Optional[int] = None
    difficulty: Optional[str] = None
    route: Optional[str] = None
    content_slug: Optional[str] = Field(
        None,
        description="Stable slug from registry (delivery/tags/content_id) for client-side resolution.",
    )
    delivery: Optional[Dict[str, Any]] = Field(
        None,
        description="Subset of json_blob.delivery: route, slug, media_steps when present.",
    )
    score: Optional[float] = None
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=False)


class RecommendationMappingResponse(BaseModel):
    """Response from recommendation mapping (primary + secondary)."""

    primary_recommendations: List[RecommendationCard] = Field(default_factory=list)
    secondary_recommendations: List[RecommendationCard] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=False)
