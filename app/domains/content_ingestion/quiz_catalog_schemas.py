"""
Pydantic schemas for the Quiz Catalog endpoints.
"""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CatalogListParams(BaseModel):
    subject: Optional[str] = None
    grade: Optional[str] = None
    curriculum: Optional[str] = None
    q: Optional[str] = None  # search: name, description, subject
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class TopicsRequest(BaseModel):
    pack_ids: List[UUID]


class ScopePreviewRequest(BaseModel):
    pack_ids: List[UUID]
    topics: List[str] = []
    refinement: Optional[str] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CatalogBookCard(BaseModel):
    id: UUID
    title: str
    authors: Optional[str]
    publisher: Optional[str]
    subject: Optional[str]
    grade: Optional[str]
    curriculum: Optional[str]
    indexed_sections: int
    document_count: int
    grades: List[str]

    class Config:
        from_attributes = True


class CatalogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CatalogBookCard]


class TopicStrand(BaseModel):
    label: str
    count: int


class TopicsResponse(BaseModel):
    topics: List[TopicStrand]
    pack_count: int


class ScopePreviewResponse(BaseModel):
    sources_count: int
    topics_count: int
    estimated_segments: int
    matched_pack_ids: List[UUID]
