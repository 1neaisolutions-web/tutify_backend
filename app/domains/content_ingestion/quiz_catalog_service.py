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
from app.domains.external_context.grade_utils import grade_filter_matches
from app.domains.external_context.subject_utils import subjects_match
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.document_topics_service import resolve_topic_ids_with_descendants
from app.domains.content_ingestion.scope_query import build_scope_chunk_filters, count_scoped_chunks
from app.domains.content_ingestion.models import Chunk, ContentPack, Document, DocumentTopic
from app.domains.content_ingestion.quiz_catalog_schemas import (
    CatalogBookCard,
    CatalogListParams,
    CatalogStructureResponse,
    DocumentStructure,
    PackStructure,
    PerDocumentScopePreview,
    ScopePreviewRequest,
    ScopePreviewResponse,
    TopicNode,
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


def _pack_matches_search(pack: ContentPack, q: str) -> bool:
    term = q.strip().lower()
    if not term:
        return True
    haystacks = [
        pack.name or "",
        pack.description or "",
        pack.subject or "",
    ]
    return any(term in h.lower() for h in haystacks)


def _pack_matches_subject(pack: ContentPack, subject: Optional[str]) -> bool:
    if not subject or not str(subject).strip():
        return True
    if not pack.subject:
        return False
    return subjects_match(subject, pack.subject)


def _pack_matches_grade(pack: ContentPack, grade: Optional[str]) -> bool:
    if not grade or not str(grade).strip():
        return True
    return grade_filter_matches(pack.grade, grade)


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
    ) -> Tuple[List[ContentPack], int, List[ContentPack]]:
        """
        Return a paginated list of active ContentPacks that have at least one
        published Document, optionally filtered by subject / grade / curriculum
        and a free-text search term.

        Returns:
            (items, total_count, near_matches) — ORM objects ready for
            `build_catalog_card`. near_matches is populated when strict filtering
            yields no primary matches and include_near_matches is True.
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

        if params.curriculum:
            query = query.filter(ContentPack.curriculum == params.curriculum)

        query = query.order_by(ContentPack.name.asc())
        all_packs: List[ContentPack] = query.all()

        near_matches: List[ContentPack] = []

        if params.strict:
            filtered = [
                p
                for p in all_packs
                if _pack_matches_subject(p, params.subject)
                and _pack_matches_grade(p, params.grade)
            ]
            if (
                params.include_near_matches
                and not filtered
                and params.subject
                and str(params.subject).strip()
            ):
                near_matches = [
                    p
                    for p in all_packs
                    if _pack_matches_subject(p, params.subject)
                    and not _pack_matches_grade(p, params.grade)
                ]
        else:
            filtered = list(all_packs)

        if params.q and params.q.strip():
            filtered = [p for p in filtered if _pack_matches_search(p, params.q)]

        total: int = len(filtered)
        offset = (params.page - 1) * params.page_size
        items: List[ContentPack] = filtered[offset : offset + params.page_size]

        logger.info(
            "quiz_catalog_get_catalog",
            extra={
                "tenant_id": str(tenant_id),
                "subject": params.subject,
                "grade": params.grade,
                "curriculum": params.curriculum,
                "q": params.q,
                "strict": params.strict,
                "include_near_matches": params.include_near_matches,
                "page": params.page,
                "page_size": params.page_size,
                "total": total,
                "near_matches": len(near_matches),
                "returned": len(items),
            },
        )
        return items, total, near_matches

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

    def _build_topic_tree(
        self,
        topics: List[DocumentTopic],
        *,
        exclude_fallback_topics: bool = True,
    ) -> List[TopicNode]:
        """Build hierarchical TopicNode list from flat DocumentTopic rows."""
        visible = [t for t in topics if t.chunk_count > 0]
        if exclude_fallback_topics:
            visible = [t for t in visible if not t.topic_key.startswith("scope:pages")]
        by_key = {t.topic_key: t for t in visible}
        children_map: dict[str, list[DocumentTopic]] = {}
        roots: list[DocumentTopic] = []
        for t in visible:
            if t.parent_key and t.parent_key in by_key:
                children_map.setdefault(t.parent_key, []).append(t)
            else:
                roots.append(t)
        roots.sort(key=lambda x: x.sort_order)

        def to_node(row: DocumentTopic) -> TopicNode:
            kids = sorted(children_map.get(row.topic_key, []), key=lambda x: x.sort_order)
            return TopicNode(
                id=row.id,
                topic_key=row.topic_key,
                display_title=row.display_title,
                level=row.level,
                chunk_count=row.chunk_count,
                start_page=row.start_page_pdf,
                end_page=row.end_page_pdf,
                children=[to_node(k) for k in kids if k.chunk_count > 0],
            )

        return [to_node(r) for r in roots]

    def get_catalog_structure(
        self,
        tenant_id: UUID,
        pack_ids: List[UUID],
        *,
        exclude_fallback_topics: bool = True,
    ) -> CatalogStructureResponse:
        """Return per-pack hierarchical document topic trees with stable UUIDs."""
        if not pack_ids:
            return CatalogStructureResponse(packs=[])

        valid_packs: List[ContentPack] = (
            self.db.query(ContentPack)
            .filter(
                ContentPack.id.in_(pack_ids),
                ContentPack.tenant_id == tenant_id,
                ContentPack.is_active.is_(True),
            )
            .order_by(ContentPack.name.asc())
            .all()
        )
        if not valid_packs:
            return CatalogStructureResponse(packs=[])

        pack_structures: List[PackStructure] = []
        for pack in valid_packs:
            documents: List[Document] = (
                self.db.query(Document)
                .filter(
                    Document.pack_id == pack.id,
                    Document.status == DocumentStatus.PUBLISHED.value,
                    Document.tenant_id == tenant_id,
                )
                .order_by(Document.filename.asc())
                .all()
            )
            doc_structures: List[DocumentStructure] = []
            for doc in documents:
                topics: List[DocumentTopic] = (
                    self.db.query(DocumentTopic)
                    .filter(DocumentTopic.document_id == doc.id)
                    .order_by(DocumentTopic.sort_order.asc())
                    .all()
                )
                total_chunks = (
                    self.db.query(func.count(Chunk.id))
                    .filter(Chunk.document_id == doc.id)
                    .scalar()
                    or 0
                )
                has_fallbacks = any(
                    t.topic_key.startswith("scope:pages") for t in topics if t.chunk_count > 0
                )
                doc_structures.append(
                    DocumentStructure(
                        document_id=doc.id,
                        document_title=doc.title or doc.filename,
                        total_chunks=total_chunks,
                        topic_tree=self._build_topic_tree(
                            topics, exclude_fallback_topics=exclude_fallback_topics
                        ),
                        has_page_bin_fallbacks=has_fallbacks,
                    )
                )
            pack_structures.append(
                PackStructure(
                    pack_id=pack.id,
                    pack_name=pack.name,
                    subject=pack.subject,
                    grade=pack.grade,
                    documents=doc_structures,
                )
            )

        return CatalogStructureResponse(packs=pack_structures)

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

        clean_topics = [t.strip() for t in req.topics if t and t.strip()]

        estimated_segments, scope = count_scoped_chunks(
            self.db,
            tenant_id=tenant_id,
            pack_ids=matched_pack_ids,
            topic_ids=req.topic_ids or None,
            topic_strings=clean_topics if not req.topic_ids else None,
            include_sub_topics=req.include_sub_topics,
            refinement=req.refinement,
        )
        apply_topic_filter = scope.applied_topic_filter
        count_filters = list(scope.filters)

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

        topics_count: int = 0
        if req.topic_ids:
            topics_count = len(
                resolve_topic_ids_with_descendants(
                    self.db,
                    req.topic_ids,
                    include_sub_topics=req.include_sub_topics,
                )
            )
        elif apply_topic_filter:
            topics_count = len([t for t in clean_topics if t != QUIZ_CATALOG_FULL_TEXT_STRAND])
        else:
            topics_count = (
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

        per_document: List[PerDocumentScopePreview] = []
        doc_rows = (
            self.db.query(
                Document.id,
                func.coalesce(Document.title, Document.filename),
                func.count(Chunk.id),
            )
            .join(Chunk, Chunk.document_id == Document.id)
            .filter(
                Document.pack_id.in_(matched_pack_ids),
                Document.status == DocumentStatus.PUBLISHED.value,
                Document.tenant_id == tenant_id,
                *count_filters,
            )
            .group_by(Document.id, Document.title, Document.filename)
            .all()
        )
        for doc_id, doc_title, chunk_count in doc_rows:
            topics_matched = 0
            if req.topic_ids:
                resolved = resolve_topic_ids_with_descendants(
                    self.db, req.topic_ids, include_sub_topics=req.include_sub_topics
                )
                topics_matched = (
                    self.db.query(func.count(func.distinct(Chunk.topic_fk)))
                    .filter(
                        Chunk.document_id == doc_id,
                        Chunk.topic_fk.in_(resolved),
                        *([func.lower(Chunk.text).ilike(f"%{req.refinement.strip().lower()}%")]
                          if req.refinement and req.refinement.strip() else []),
                    )
                    .scalar()
                    or 0
                )
            per_document.append(
                PerDocumentScopePreview(
                    document_id=doc_id,
                    document_title=doc_title,
                    chunk_count=int(chunk_count),
                    topics_matched=int(topics_matched),
                )
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
            per_document=per_document,
        )
