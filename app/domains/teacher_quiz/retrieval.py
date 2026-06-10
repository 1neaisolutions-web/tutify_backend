from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Chunk, ContentPack, Document, DocumentTopic
from app.domains.content_ingestion.quiz_catalog_service import (
    QUIZ_CATALOG_FULL_TEXT_STRAND,
    _topic_strings_apply_chunk_filter,
)
from app.domains.content_ingestion.topic_scope import RetrievalScopeError, expand_scope_topic_ids


@dataclass(frozen=True)
class RetrievalResult:
    context_text: str
    citations: List[Dict[str, str]]
    warnings: List[str]
    metadata: Dict[str, Any]


def _page_range(meta: Dict[str, Any]) -> str:
    start = meta.get("page_start_pdf")
    end = meta.get("page_end_pdf")
    if start is not None and end is not None:
        return f"{start}-{end}"
    if start is not None:
        return str(start)
    if end is not None:
        return str(end)
    return ""


def _safe_topic_filter_clause(topics: List[str]):
    clean = [t.strip() for t in topics if t and t.strip()]
    if not _topic_strings_apply_chunk_filter(clean):
        return None
    clauses = []
    for t in clean:
        if t == QUIZ_CATALOG_FULL_TEXT_STRAND:
            continue
        clauses.append(Chunk.topic_title.ilike(f"%{t}%"))
        clauses.append(func.coalesce(Document.title, "") == t)
        clauses.append(Document.filename == t)
    if not clauses:
        return None
    return or_(*clauses)


class QuizRetrievalService:
    """Retrieval for quiz generation using stable topic_fk when enabled."""

    def __init__(self, db: Session):
        self.db = db

    def validate_pack_ownership(self, tenant_id: UUID, pack_ids: List[UUID]) -> List[UUID]:
        if not pack_ids:
            return []
        rows = (
            self.db.query(ContentPack.id)
            .filter(
                ContentPack.id.in_(pack_ids),
                ContentPack.tenant_id == tenant_id,
                ContentPack.is_active.is_(True),
            )
            .all()
        )
        return [r[0] for r in rows]

    def retrieve(
        self,
        *,
        tenant_id: UUID,
        pack_ids: List[UUID],
        topics: List[str],
        scope_topic_ids: Optional[List[UUID]] = None,
        refinement: Optional[str],
        max_chunks: int = 18,
        include_sub_topics: bool = True,
        generate_without_sources: bool = False,
    ) -> RetrievalResult:
        warnings: List[str] = []
        meta: Dict[str, Any] = {}

        valid_pack_ids = self.validate_pack_ownership(tenant_id, pack_ids)
        if not valid_pack_ids:
            return RetrievalResult(
                context_text="",
                citations=[],
                warnings=["No accessible packs found for this tenant."],
                metadata={"pack_ids": [], "applied_topic_filter": False},
            )

        base_q = (
            self.db.query(Chunk, Document, ContentPack)
            .join(Document, Chunk.document_id == Document.id)
            .join(ContentPack, Document.pack_id == ContentPack.id)
            .filter(
                Document.pack_id.in_(valid_pack_ids),
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.PUBLISHED.value,
            )
        )

        applied_topic = False
        q = base_q
        resolved_ids: List[UUID] = []

        use_topic_ids = bool(
            scope_topic_ids
            and settings.SCOPE_BY_TOPIC_ID_ENABLED
        )
        if use_topic_ids:
            resolved_ids = expand_scope_topic_ids(
                self.db, scope_topic_ids or [], include_sub_topics=include_sub_topics
            )
            if resolved_ids:
                applied_topic = True
                q = q.filter(Chunk.topic_fk.in_(resolved_ids))
        else:
            clause = _safe_topic_filter_clause(topics)
            if clause is not None:
                applied_topic = True
                q = q.filter(clause)

        use_semantic = (
            refinement
            and refinement.strip()
            and settings.EMBEDDING_PROVIDER != "fake"
        )
        if refinement and refinement.strip() and not use_semantic:
            term = f"%{refinement.strip().lower()}%"
            q = q.filter(func.lower(Chunk.text).ilike(term))
            warnings.append("Semantic search unavailable; using text search instead.")

        rows = (
            q.order_by(Chunk.page_start_pdf.asc().nulls_last(), Chunk.created_at.asc().nulls_last())
            .limit(max_chunks)
            .all()
        )

        if not rows and applied_topic:
            if use_topic_ids and settings.SCOPE_BY_TOPIC_ID_ENABLED:
                raise RetrievalScopeError(
                    "No content found for selected chapters. The book may need re-processing.",
                    topic_ids=scope_topic_ids or [],
                    fallback_available=generate_without_sources,
                )
            if not use_topic_ids:
                warnings.append("Topic filter returned no chunks; widening to full pack scope.")
                rows = (
                    base_q.order_by(
                        Chunk.page_start_pdf.asc().nulls_last(),
                        Chunk.created_at.asc().nulls_last(),
                    )
                    .limit(max_chunks)
                    .all()
                )
                applied_topic = False

        topic_titles: Dict[UUID, str] = {}
        if rows and any(r[0].topic_fk for r in rows):
            fk_ids = [r[0].topic_fk for r in rows if r[0].topic_fk]
            for dt in self.db.query(DocumentTopic).filter(DocumentTopic.id.in_(fk_ids)).all():
                topic_titles[dt.id] = dt.display_title

        citations: List[Dict[str, str]] = []
        context_parts: List[str] = []
        current_doc_header: Optional[str] = None

        for chunk, doc, pack in rows:
            topic_label = topic_titles.get(chunk.topic_fk, chunk.topic_title or "")
            doc_header = f"=== {doc.title or doc.filename} (Pack: {pack.name}) ==="
            if doc_header != current_doc_header:
                context_parts.append(doc_header)
                current_doc_header = doc_header

            page_lo = chunk.page_start_pdf or "?"
            page_hi = chunk.page_end_pdf or page_lo
            section_header = f"--- Chapter: {topic_label} | Pages {page_lo}–{page_hi} ---"
            context_parts.append(section_header + "\n" + (chunk.text or ""))

            citations.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "pack_id": str(doc.pack_id),
                    "document_title": doc.title or doc.filename,
                    "topic_title": topic_label,
                    "page_range": _page_range(
                        {
                            "page_start_pdf": chunk.page_start_pdf,
                            "page_end_pdf": chunk.page_end_pdf,
                        }
                    ),
                }
            )

        meta.update(
            {
                "pack_ids": [str(x) for x in valid_pack_ids],
                "applied_topic_filter": applied_topic,
                "topic_count": len(resolved_ids) if use_topic_ids else len([t for t in topics if t and t.strip()]),
                "chunk_count": len(rows),
                "refinement": refinement or "",
                "scope_mode": "topic_fk" if use_topic_ids else "legacy_string",
            }
        )

        return RetrievalResult(
            context_text="\n\n".join(context_parts),
            citations=citations,
            warnings=warnings,
            metadata=meta,
        )
