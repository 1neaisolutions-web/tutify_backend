"""
Service layer for the Quiz Catalog endpoints.

Provides tenant-scoped catalog browsing, topic extraction, and scope preview
without any N+1 queries (all counts are resolved via subqueries/joins).
"""
import re
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.core.logging import get_logger
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Chunk, ContentPack, Document
from app.domains.content_ingestion.quiz_catalog_schemas import (
    CatalogBookCard,
    CatalogListParams,
    ScopePreviewRequest,
    ScopePreviewResponse,
    TopicStrand,
    TopicsResponse,
)

logger = get_logger(__name__)

# Pre-compiled separator pattern for grade splitting
_GRADE_SEP = re.compile(r"[,/\-]")

# When chunks exist but chapter_map / chunk.topic_title produced no strands, the UI still
# needs a selectable scope. Selecting this strand disables topic_title filtering (full pack).
QUIZ_CATALOG_FULL_TEXT_STRAND = "Entire book (no chapter map)"
_PAGE_RANGE_LABEL_RE = re.compile(r".+\s·\spp\.\s*\d+\s*[–-]\s*\d+$", re.IGNORECASE)


def _chunks_match_topic_strings_clause(topic_strings: List[str]) -> ColumnElement:
    """OR across topics: chunk topic_title ilike OR exact document title/filename match."""
    clauses: List[ColumnElement] = []
    for topic in topic_strings:
        if topic == QUIZ_CATALOG_FULL_TEXT_STRAND:
            continue
        clauses.append(
            or_(
                Chunk.topic_title.ilike(f"%{topic}%"),
                func.coalesce(Document.title, "") == topic,
                Document.filename == topic,
            )
        )
    assert clauses, "filter clause requires at least one non-sentinel topic string"
    return or_(*clauses)


def _topic_strings_apply_chunk_filter(topic_strings: List[str]) -> bool:
    """False when retrieval should include all chunks (full-text strand or no selection)."""
    if not topic_strings:
        return False
    if QUIZ_CATALOG_FULL_TEXT_STRAND in topic_strings:
        return False
    return True


def _is_page_range_fallback_label(label: str) -> bool:
    """Detect generic fallback labels like '<doc> · pp. 1–10'."""
    return bool(_PAGE_RANGE_LABEL_RE.match((label or "").strip()))


class QuizCatalogService:
    """
    Service for the quiz catalog domain.

    All methods are tenant-scoped; callers must pass a valid tenant_id that
    comes from the authenticated user.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_catalog(
        self,
        tenant_id: UUID,
        params: CatalogListParams,
    ) -> Tuple[List[ContentPack], int]:
        """
        Return a paginated list of active ContentPacks that have at least one
        published Document, optionally filtered by subject / grade / curriculum
        and a free-text search term.

        Returns:
            (items, total_count) — `items` are ORM objects ready for
            `build_catalog_card`.
        """
        published_doc_exists = (
            self.db.query(Document)
            .filter(
                Document.pack_id == ContentPack.id,
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
            )
            .exists()
        )

        query = (
            self.db.query(ContentPack)
            .filter(
                ContentPack.tenant_id == tenant_id,
                ContentPack.is_active.is_(True),
                exists(published_doc_exists),
            )
        )

        if params.subject:
            query = query.filter(ContentPack.subject.ilike(f"%{params.subject}%"))

        if params.grade:
            query = query.filter(ContentPack.grade.ilike(f"%{params.grade}%"))

        if params.curriculum:
            query = query.filter(ContentPack.curriculum == params.curriculum)

        if params.q:
            term = f"%{params.q}%"
            query = query.filter(
                or_(
                    ContentPack.name.ilike(term),
                    ContentPack.description.ilike(term),
                    ContentPack.subject.ilike(term),
                )
            )

        query = query.order_by(ContentPack.name.asc())

        total: int = query.count()

        offset = (params.page - 1) * params.page_size
        items: List[ContentPack] = query.offset(offset).limit(params.page_size).all()

        logger.info(
            "quiz_catalog_get_catalog",
            extra={
                "tenant_id": str(tenant_id),
                "subject": params.subject,
                "grade": params.grade,
                "curriculum": params.curriculum,
                "q": params.q,
                "page": params.page,
                "page_size": params.page_size,
                "total": total,
                "returned": len(items),
            },
        )
        return items, total

    def get_indexed_section_count(self, pack_id: UUID) -> int:
        """
        Return the total number of Chunks that belong to published Documents
        inside the given pack.  No tenant check here — callers must have
        already verified pack ownership before exposing this number.
        """
        count: int = (
            self.db.query(func.count(Chunk.id))
            .join(Document, Chunk.document_id == Document.id)
            .filter(
                Document.pack_id == pack_id,
                Document.status == DocumentStatus.PUBLISHED.value,
            )
            .scalar()
            or 0
        )
        return count

    def get_document_count(self, pack_id: UUID, tenant_id: UUID) -> int:
        """
        Return the number of published Documents for a pack within a tenant.
        """
        count: int = (
            self.db.query(func.count(Document.id))
            .filter(
                Document.pack_id == pack_id,
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
            )
            .scalar()
            or 0
        )
        return count

    def build_catalog_card(
        self,
        pack: ContentPack,
        tenant_id: UUID,
    ) -> CatalogBookCard:
        """
        Build a ``CatalogBookCard`` from a ``ContentPack`` ORM instance.

        Author resolution order:
        1. First published Document's ``author`` field (non-empty).
        2. ``pack.pack_metadata["authors"]`` if present.
        3. ``None``.
        """
        # --- author ---
        first_doc: Optional[Document] = (
            self.db.query(Document)
            .filter(
                Document.pack_id == pack.id,
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
                Document.author.isnot(None),
                Document.author != "",
            )
            .order_by(Document.created_at.asc())
            .first()
        )
        authors: Optional[str] = None
        if first_doc and first_doc.author:
            authors = first_doc.author
        elif pack.pack_metadata:
            authors = pack.pack_metadata.get("authors") or None

        # --- publisher ---
        publisher: Optional[str] = (
            pack.pack_metadata.get("publisher") if pack.pack_metadata else None
        ) or None

        # --- grades list ---
        grades: List[str] = []
        if pack.grade:
            raw_parts = _GRADE_SEP.split(pack.grade)
            seen: dict = {}
            for part in raw_parts:
                cleaned = part.strip()
                if cleaned and cleaned not in seen:
                    seen[cleaned] = True
                    grades.append(cleaned)
            grades.sort()

        return CatalogBookCard(
            id=pack.id,
            title=pack.name,
            authors=authors,
            publisher=publisher,
            subject=pack.subject,
            grade=pack.grade,
            curriculum=pack.curriculum,
            indexed_sections=self.get_indexed_section_count(pack.id),
            document_count=self.get_document_count(pack.id, tenant_id),
            grades=grades,
        )

    def get_topics_for_packs(
        self,
        tenant_id: UUID,
        pack_ids: List[UUID],
    ) -> TopicsResponse:
        """
        Aggregate topics across all requested packs that belong to the tenant.

        Topic sources (both merged and counted):
        - ``chapter_map`` entries → ``chapter["title"]``
        - ``Chunk.topic_title`` values for published documents

        Returns a ``TopicsResponse`` with topics sorted by label.
        """
        if not pack_ids:
            return TopicsResponse(topics=[], pack_count=0)

        # Verify ownership — only keep packs that belong to this tenant
        valid_packs: List[ContentPack] = (
            self.db.query(ContentPack)
            .filter(
                ContentPack.id.in_(pack_ids),
                ContentPack.tenant_id == tenant_id,
                ContentPack.is_active.is_(True),
            )
            .all()
        )
        valid_pack_ids = [p.id for p in valid_packs]

        if not valid_pack_ids:
            logger.info(
                "quiz_catalog_get_topics_no_valid_packs",
                extra={"tenant_id": str(tenant_id), "requested": len(pack_ids)},
            )
            return TopicsResponse(topics=[], pack_count=0)

        # Fetch published documents for those packs (all at once — no N+1)
        documents: List[Document] = (
            self.db.query(Document)
            .filter(
                Document.pack_id.in_(valid_pack_ids),
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
            )
            .all()
        )
        doc_ids = [d.id for d in documents]

        # Count dict: label → occurrence count
        topic_counts: dict[str, int] = {}

        # Source 1: chapter_map titles
        for doc in documents:
            if not doc.chapter_map:
                continue
            if not isinstance(doc.chapter_map, list):
                continue
            for chapter in doc.chapter_map:
                if not isinstance(chapter, dict):
                    continue
                title: Optional[str] = chapter.get("title")
                if title and isinstance(title, str):
                    label = title.strip()
                    if len(label) >= 2:
                        topic_counts[label] = topic_counts.get(label, 0) + 1

        # Source 2: distinct Chunk.topic_title values
        if doc_ids:
            rows = (
                self.db.query(Chunk.topic_title, func.count(Chunk.id))
                .filter(
                    Chunk.document_id.in_(doc_ids),
                    Chunk.topic_title.isnot(None),
                    Chunk.topic_title != "",
                )
                .group_by(Chunk.topic_title)
                .all()
            )
            for topic_title, cnt in rows:
                if topic_title and len(topic_title.strip()) >= 2:
                    label = topic_title.strip()
                    topic_counts[label] = topic_counts.get(label, 0) + cnt

        # PDFs without a chapter map leave every chunk with topic_title NULL — still offer one strand
        # so the quiz UI can scope retrieval to the full indexed text.
        if not topic_counts and doc_ids:
            indexed_chunks: int = (
                self.db.query(func.count(Chunk.id))
                .filter(Chunk.document_id.in_(doc_ids))
                .scalar()
                or 0
            )
            if indexed_chunks > 0:
                topic_counts[QUIZ_CATALOG_FULL_TEXT_STRAND] = indexed_chunks

        # If richer topic strands exist, suppress generic page-range fallback labels
        # so quiz topic chips stay clear for teachers.
        non_fallback_labels = [lbl for lbl in topic_counts.keys() if not _is_page_range_fallback_label(lbl)]
        if non_fallback_labels:
            topic_counts = {lbl: cnt for lbl, cnt in topic_counts.items() if not _is_page_range_fallback_label(lbl)}

        topics = sorted(
            [TopicStrand(label=lbl, count=cnt) for lbl, cnt in topic_counts.items()],
            key=lambda t: t.label,
        )

        logger.info(
            "quiz_catalog_get_topics",
            extra={
                "tenant_id": str(tenant_id),
                "requested_packs": len(pack_ids),
                "valid_packs": len(valid_pack_ids),
                "topic_count": len(topics),
            },
        )
        return TopicsResponse(topics=topics, pack_count=len(valid_pack_ids))

    def get_scope_preview(
        self,
        tenant_id: UUID,
        req: ScopePreviewRequest,
    ) -> ScopePreviewResponse:
        """
        Return a lightweight preview of what a quiz generation scope would cover:

        - ``sources_count``    — number of matched published documents
        - ``topics_count``     — number of distinct topic_titles in those chunks
        - ``estimated_segments`` — actual chunk count (no magic formula)
        - ``matched_pack_ids`` — validated pack IDs that belong to this tenant
        """
        if not req.pack_ids:
            return ScopePreviewResponse(
                sources_count=0,
                topics_count=0,
                estimated_segments=0,
                matched_pack_ids=[],
            )

        # Validate ownership
        valid_packs: List[ContentPack] = (
            self.db.query(ContentPack)
            .filter(
                ContentPack.id.in_(req.pack_ids),
                ContentPack.tenant_id == tenant_id,
                ContentPack.is_active.is_(True),
            )
            .all()
        )
        matched_pack_ids = [p.id for p in valid_packs]

        if not matched_pack_ids:
            return ScopePreviewResponse(
                sources_count=0,
                topics_count=0,
                estimated_segments=0,
                matched_pack_ids=[],
            )

        # Base chunk query — published docs in these packs
        chunk_query = (
            self.db.query(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .filter(
                Document.pack_id.in_(matched_pack_ids),
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
            )
        )

        clean_topics = [t.strip() for t in req.topics if t and t.strip()]
        apply_topic_filter = _topic_strings_apply_chunk_filter(clean_topics)
        topic_clause = (
            _chunks_match_topic_strings_clause(clean_topics) if apply_topic_filter else None
        )

        if apply_topic_filter and topic_clause is not None:
            chunk_query = chunk_query.filter(topic_clause)

        # Count total chunks (estimated_segments) — single query
        count_filters: List[ColumnElement] = []
        if apply_topic_filter and topic_clause is not None:
            count_filters.append(topic_clause)

        estimated_segments: int = (
            self.db.query(func.count(Chunk.id))
            .join(Document, Chunk.document_id == Document.id)
            .filter(
                Document.pack_id.in_(matched_pack_ids),
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
                *count_filters,
            )
            .scalar()
            or 0
        )

        # Count distinct document sources
        sources_count: int = (
            self.db.query(func.count(func.distinct(Document.id)))
            .join(Chunk, Chunk.document_id == Document.id)
            .filter(
                Document.pack_id.in_(matched_pack_ids),
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
                *count_filters,
            )
            .scalar()
            or 0
        )

        # Count distinct chunk topic_title values (only meaningful when filtering by real strands)
        topics_count: int = (
            self.db.query(func.count(func.distinct(Chunk.topic_title)))
            .join(Document, Chunk.document_id == Document.id)
            .filter(
                Document.pack_id.in_(matched_pack_ids),
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
                Chunk.topic_title.isnot(None),
                Chunk.topic_title != "",
                *count_filters,
            )
            .scalar()
            or 0
        )

        logger.info(
            "quiz_catalog_scope_preview",
            extra={
                "tenant_id": str(tenant_id),
                "requested_packs": len(req.pack_ids),
                "matched_packs": len(matched_pack_ids),
                "topics_filter_count": len(clean_topics),
                "estimated_segments": estimated_segments,
            },
        )

        return ScopePreviewResponse(
            sources_count=sources_count,
            topics_count=topics_count,
            estimated_segments=estimated_segments,
            matched_pack_ids=matched_pack_ids,
        )
