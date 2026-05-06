"""
Pydantic schemas for PixGen domain.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GenerateImageRequest(BaseModel):
    """Request payload for single generation."""

    prompt: str = Field(..., min_length=1, max_length=4000)
    stylePreset: str = Field(..., min_length=1, max_length=120)
    aspectRatio: str = Field(..., min_length=1, max_length=50)


class GenerateBatchRequest(GenerateImageRequest):
    """Request payload for batch generation."""

    batchSize: int = Field(4, ge=1, le=8)


class GenerationResponse(BaseModel):
    """Response for one generated image."""

    id: UUID
    imageUrl: Optional[str] = None
    status: str
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchGenerationResponse(BaseModel):
    """Response for batch generation."""

    items: List[GenerationResponse]


class MyGenerationsResponse(BaseModel):
    """Response for user generation history."""

    items: List[GenerationResponse]


class GenerationStatusResponse(GenerationResponse):
    """Detailed status response for one generation."""

    provider: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PixGenGenerationDetailResponse(BaseModel):
    """Full saved generation row for history restore / detail GET."""

    id: UUID
    imageUrl: Optional[str] = None
    prompt: str
    stylePreset: str
    aspectRatio: str
    status: str
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)
