"""
Pydantic schemas for the Quiz Catalog endpoints.
"""
from typing import Any, Dict, List, Optional
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
    strict: bool = True
    include_near_matches: bool = False
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class TopicsRequest(BaseModel):
    pack_ids: List[UUID]


class CatalogStructureRequest(BaseModel):
    pack_ids: List[UUID]


class ScopePreviewRequest(BaseModel):
    pack_ids: List[UUID]
    topic_ids: List[UUID] = []
    topics: List[str] = []
    refinement: Optional[str] = None
    include_sub_topics: bool = True


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
    near_matches: List[CatalogBookCard] = Field(default_factory=list)


class TopicStrand(BaseModel):
    label: str
    count: int


class TopicsResponse(BaseModel):
    topics: List[TopicStrand]
    pack_count: int


class TopicNode(BaseModel):
    id: UUID
    topic_key: str
    display_title: str
    level: int
    chunk_count: int
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    children: List["TopicNode"] = Field(default_factory=list)


class DocumentStructure(BaseModel):
    document_id: UUID
    document_title: str
    total_chunks: int
    topic_tree: List[TopicNode]
    has_page_bin_fallbacks: bool


class PackStructure(BaseModel):
    pack_id: UUID
    pack_name: str
    subject: Optional[str]
    grade: Optional[str]
    documents: List[DocumentStructure]


class CatalogStructureResponse(BaseModel):
    packs: List[PackStructure]


class PerDocumentScopePreview(BaseModel):
    document_id: UUID
    document_title: str
    chunk_count: int
    topics_matched: int


class ScopePreviewResponse(BaseModel):
    sources_count: int
    topics_count: int
    estimated_segments: int
    matched_pack_ids: List[UUID]
    per_document: List[PerDocumentScopePreview] = Field(default_factory=list)


TopicNode.model_rebuild()
