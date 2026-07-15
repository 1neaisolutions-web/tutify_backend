"""
Unified scope filtering for quiz catalog preview and quiz retrieval.

Single code path: topic_fk IN resolved_ids + optional page-range guard + refinement.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, true
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import ColumnElement

from app.core.config import settings
from app.domains.content_ingestion.document_topics_service import resolve_topic_ids_with_descendants
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Chunk, ContentPack, Document, DocumentTopic

QUIZ_CATALOG_FULL_TEXT_STRAND = "Entire book (no chapter map)"


def _chunks_match_topic_strings_clause(topic_strings: List[str]) -> ColumnElement:
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
    if not topic_strings:
        return False
    if QUIZ_CATALOG_FULL_TEXT_STRAND in topic_strings:
        return False
    return True


@dataclass(frozen=True)
class ScopeFilterResult:
    """Result of building scope filters."""

    filters: Tuple[ColumnElement, ...]
    applied_topic_filter: bool
    resolved_topic_ids: List[UUID]
    scope_mode: str
    scope_page_ranges: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    page_range_guard_applied: bool = False


def resolve_scope_topic_ids(
    db: Session,
    topic_ids: Sequence[UUID],
    *,
    include_sub_topics: bool = True,
) -> List[UUID]:
    return resolve_topic_ids_with_descendants(
        db, list(topic_ids), include_sub_topics=include_sub_topics
    )


def _chunk_midpoint_expr() -> ColumnElement:
    """SQL expression for chunk page midpoint (null-safe)."""
    lo = func.coalesce(Chunk.page_start_pdf, Chunk.page_end_pdf)
    hi = func.coalesce(Chunk.page_end_pdf, Chunk.page_start_pdf)
    return (lo + hi) / 2.0


def _scope_midpoint_in_ranges_clause(topic_rows: Sequence[DocumentTopic]) -> ColumnElement:
    """
    Chunk midpoint must fall within the union of selected scope topic page ranges.
    Chunks with no page numbers pass through (logged by callers).
    """
    mid = _chunk_midpoint_expr()
    range_clauses: List[ColumnElement] = []
    for row in topic_rows:
        lo = row.start_page_pdf
        hi = row.end_page_pdf
        if lo is not None and hi is not None:
            range_clauses.append(and_(mid >= lo, mid <= hi))
        elif lo is not None:
            range_clauses.append(mid >= lo)
        elif hi is not None:
            range_clauses.append(mid <= hi)

    if not range_clauses:
        return true()

    no_pages = and_(Chunk.page_start_pdf.is_(None), Chunk.page_end_pdf.is_(None))
    return or_(no_pages, or_(*range_clauses))


def _load_scope_topic_rows(db: Session, topic_ids: Sequence[UUID]) -> List[DocumentTopic]:
    if not topic_ids:
        return []
    return (
        db.query(DocumentTopic)
        .filter(DocumentTopic.id.in_(list(topic_ids)))
        .order_by(DocumentTopic.sort_order.asc().nulls_last(), DocumentTopic.start_page_pdf.asc())
        .all()
    )


def scope_page_ranges_metadata(topic_rows: Sequence[DocumentTopic]) -> List[Dict[str, Any]]:
    return [
        {
            "topic_id": str(row.id),
            "topic_key": row.topic_key,
            "display_title": row.display_title,
            "start_page_pdf": row.start_page_pdf,
            "end_page_pdf": row.end_page_pdf,
            "level": row.level,
        }
        for row in topic_rows
    ]


def build_scope_chunk_filters(
    db: Session,
    *,
    tenant_id: UUID,
    pack_ids: List[UUID],
    topic_ids: Optional[List[UUID]] = None,
    topic_strings: Optional[List[str]] = None,
    include_sub_topics: bool = True,
    refinement: Optional[str] = None,
    apply_page_range_guard: bool = True,
) -> ScopeFilterResult:
    """
    Build SQLAlchemy filter clauses for scoped chunk queries.

    When topic_ids provided and SCOPE_BY_TOPIC_ID enabled (or strict mode), uses topic_fk.
    Legacy string path only when strict mode off and no topic_ids.
    """
    filters: List[ColumnElement] = []
    resolved: List[UUID] = []
    applied = False
    scope_mode = "none"
    scope_ranges: Tuple[Dict[str, Any], ...] = ()
    guard_applied = False

    strict = bool(getattr(settings, "QUIZ_STRICT_SCOPE_ONLY", True))
    use_ids = bool(
        topic_ids
        and (settings.SCOPE_BY_TOPIC_ID_ENABLED or strict)
    )

    if use_ids:
        resolved = resolve_scope_topic_ids(
            db, topic_ids or [], include_sub_topics=include_sub_topics
        )
        if topic_ids:
            applied = True
            scope_mode = "topic_fk"
            if resolved:
                filters.append(Chunk.topic_fk.in_(resolved))
                scope_topic_rows = _load_scope_topic_rows(db, resolved)
                scope_ranges = tuple(scope_page_ranges_metadata(scope_topic_rows))
                guard_on = apply_page_range_guard and bool(
                    getattr(settings, "SCOPE_PAGE_RANGE_GUARD_ENABLED", False)
                )
                if guard_on and scope_topic_rows:
                    filters.append(_scope_midpoint_in_ranges_clause(scope_topic_rows))
                    guard_applied = True
            else:
                # Force zero-match filter so callers get 0 chunks / RetrievalScopeError
                filters.append(Chunk.topic_fk.in_([]))
    elif not strict:
        clean = [t.strip() for t in (topic_strings or []) if t and t.strip()]
        if _topic_strings_apply_chunk_filter(clean):
            applied = True
            scope_mode = "legacy_string"
            filters.append(_chunks_match_topic_strings_clause(clean))

    if refinement and refinement.strip():
        term = f"%{refinement.strip().lower()}%"
        filters.append(func.lower(Chunk.text).ilike(term))

    return ScopeFilterResult(
        filters=tuple(filters),
        applied_topic_filter=applied,
        resolved_topic_ids=resolved,
        scope_mode=scope_mode,
        scope_page_ranges=scope_ranges,
        page_range_guard_applied=guard_applied,
    )


def _base_chunk_query(
    db: Session,
    *,
    tenant_id: UUID,
    pack_ids: List[UUID],
) -> Query:
    return (
        db.query(Chunk, Document, ContentPack)
        .join(Document, Chunk.document_id == Document.id)
        .join(ContentPack, Document.pack_id == ContentPack.id)
        .filter(
            Document.pack_id.in_(pack_ids),
            Document.tenant_id == tenant_id,
            Document.status == DocumentStatus.PUBLISHED.value,
        )
    )


def count_scoped_chunks(
    db: Session,
    *,
    tenant_id: UUID,
    pack_ids: List[UUID],
    topic_ids: Optional[List[UUID]] = None,
    topic_strings: Optional[List[str]] = None,
    include_sub_topics: bool = True,
    refinement: Optional[str] = None,
    apply_page_range_guard: bool = True,
) -> Tuple[int, ScopeFilterResult]:
    scope = build_scope_chunk_filters(
        db,
        tenant_id=tenant_id,
        pack_ids=pack_ids,
        topic_ids=topic_ids,
        topic_strings=topic_strings,
        include_sub_topics=include_sub_topics,
        refinement=refinement,
        apply_page_range_guard=apply_page_range_guard,
    )
    count: int = (
        db.query(func.count(Chunk.id))
        .join(Document, Chunk.document_id == Document.id)
        .filter(
            Document.pack_id.in_(pack_ids),
            Document.status == DocumentStatus.PUBLISHED.value,
            Document.tenant_id == tenant_id,
            *scope.filters,
        )
        .scalar()
        or 0
    )
    return count, scope


def _stratified_sample_chunks(
    rows: List[Tuple[Chunk, Document, ContentPack]],
    limit: int,
    seed: Optional[str] = None,
) -> List[Tuple[Chunk, Document, ContentPack]]:
    """Evenly sample chunks across topic_fk groups (deterministic when seed set)."""
    if len(rows) <= limit:
        return rows

    groups: dict[Optional[UUID], List[Tuple[Chunk, Document, ContentPack]]] = {}
    for row in rows:
        fk = row[0].topic_fk
        groups.setdefault(fk, []).append(row)

    for g in groups.values():
        g.sort(key=lambda r: (r[0].page_start_pdf or 0, r[0].created_at or r[0].chunk_id))

    group_keys = sorted(groups.keys(), key=lambda k: str(k))
    if seed:
        h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
        group_keys = sorted(group_keys, key=lambda k: hash(str(k) + str(h)))

    picked: List[Tuple[Chunk, Document, ContentPack]] = []
    idx = 0
    while len(picked) < limit:
        added = False
        for key in group_keys:
            bucket = groups[key]
            if idx < len(bucket):
                picked.append(bucket[idx])
                added = True
                if len(picked) >= limit:
                    break
        if not added:
            break
        idx += 1

    picked.sort(key=lambda r: (r[0].page_start_pdf or 0, r[0].created_at or r[0].chunk_id))
    return picked[:limit]


def fetch_scoped_chunks(
    db: Session,
    *,
    tenant_id: UUID,
    pack_ids: List[UUID],
    topic_ids: Optional[List[UUID]] = None,
    topic_strings: Optional[List[str]] = None,
    include_sub_topics: bool = True,
    refinement: Optional[str] = None,
    limit: int = 18,
    stratified: bool = True,
    seed: Optional[str] = None,
) -> Tuple[List[Tuple[Chunk, Document, ContentPack]], ScopeFilterResult]:
    scope = build_scope_chunk_filters(
        db,
        tenant_id=tenant_id,
        pack_ids=pack_ids,
        topic_ids=topic_ids,
        topic_strings=topic_strings,
        include_sub_topics=include_sub_topics,
        refinement=refinement,
    )
    q = _base_chunk_query(db, tenant_id=tenant_id, pack_ids=pack_ids)
    if scope.filters:
        q = q.filter(*scope.filters)

    if stratified and limit > 0:
        all_rows = q.order_by(
            Chunk.page_start_pdf.asc().nulls_last(),
            Chunk.created_at.asc().nulls_last(),
        ).all()
        rows = _stratified_sample_chunks(all_rows, limit, seed=seed)
    else:
        rows = (
            q.order_by(
                Chunk.page_start_pdf.asc().nulls_last(),
                Chunk.created_at.asc().nulls_last(),
            )
            .limit(limit)
            .all()
        )

    return rows, scope


def count_scoped_chunks_diagnostics(
    db: Session,
    *,
    tenant_id: UUID,
    pack_ids: List[UUID],
    topic_ids: Optional[List[UUID]] = None,
    topic_strings: Optional[List[str]] = None,
    include_sub_topics: bool = True,
    refinement: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare chunk counts with and without page-range guard."""
    before, scope_off = count_scoped_chunks(
        db,
        tenant_id=tenant_id,
        pack_ids=pack_ids,
        topic_ids=topic_ids,
        topic_strings=topic_strings,
        include_sub_topics=include_sub_topics,
        refinement=refinement,
        apply_page_range_guard=False,
    )
    after, scope_on = count_scoped_chunks(
        db,
        tenant_id=tenant_id,
        pack_ids=pack_ids,
        topic_ids=topic_ids,
        topic_strings=topic_strings,
        include_sub_topics=include_sub_topics,
        refinement=refinement,
        apply_page_range_guard=True,
    )
    return {
        "chunks_before_page_guard": before,
        "chunks_after_page_guard": after,
        "excluded_by_page_guard": max(0, before - after),
        "scope_page_ranges": list(scope_on.scope_page_ranges),
        "page_range_guard_applied": scope_on.page_range_guard_applied,
    }


def validate_scope_topic_ids_for_tenant(
    db: Session,
    *,
    tenant_id: UUID,
    pack_ids: List[UUID],
    topic_ids: List[UUID],
) -> List[UUID]:
    """Return topic IDs that belong to published documents in the given packs."""
    if not topic_ids or not pack_ids:
        return []
    rows = (
        db.query(DocumentTopic.id)
        .join(Document, DocumentTopic.document_id == Document.id)
        .filter(
            DocumentTopic.id.in_(topic_ids),
            Document.pack_id.in_(pack_ids),
            Document.tenant_id == tenant_id,
            Document.status == DocumentStatus.PUBLISHED.value,
        )
        .all()
    )
    return [r[0] for r in rows]
