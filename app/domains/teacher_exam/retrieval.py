from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Chunk, ContentPack, Document
from app.domains.content_ingestion.quiz_catalog_service import (
    QUIZ_CATALOG_FULL_TEXT_STRAND,
    _topic_strings_apply_chunk_filter,
)


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


class ExamRetrievalService:
    """Same retrieval strategy as quiz generation (published chunks + topic filters)."""

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
        refinement: Optional[str],
        max_chunks: int = 18,
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
            self.db.query(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .filter(
                Document.pack_id.in_(valid_pack_ids),
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.PUBLISHED.value,
            )
        )

        clause = _safe_topic_filter_clause(topics)
        applied_topic = False
        q = base_q
        if clause is not None:
            applied_topic = True
            q = q.filter(clause)

        if refinement and refinement.strip():
            term = f"%{refinement.strip().lower()}%"
            q = q.filter(func.lower(Chunk.text).ilike(term))

        rows = (
            q.order_by(Chunk.page_start_pdf.asc().nulls_last(), Chunk.created_at.asc().nulls_last())
            .limit(max_chunks)
            .all()
        )

        if not rows and applied_topic:
            warnings.append("Topic filter returned no chunks; widening to full pack scope.")
            rows = (
                base_q.order_by(Chunk.page_start_pdf.asc().nulls_last(), Chunk.created_at.asc().nulls_last())
                .limit(max_chunks)
                .all()
            )
            applied_topic = False

        citations: List[Dict[str, str]] = []
        context_parts: List[str] = []
        for (chunk, doc) in rows:
            cmeta = {
                "chunk_id": str(chunk.id),
                "document_id": str(doc.id),
                "pack_id": str(doc.pack_id),
                "page_start_pdf": getattr(chunk, "page_start_pdf", None),
                "page_end_pdf": getattr(chunk, "page_end_pdf", None),
                "role": getattr(chunk, "role", None),
            }
            citations.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "pack_id": str(doc.pack_id),
                    "page_range": _page_range(cmeta),
                }
            )
            prefix = f"[doc: {doc.title or doc.filename} · pages {citations[-1]['page_range']}]"
            context_parts.append(prefix + "\n" + (chunk.text or ""))

        meta.update(
            {
                "pack_ids": [str(x) for x in valid_pack_ids],
                "applied_topic_filter": applied_topic,
                "topic_count": len([t for t in topics if t and t.strip()]),
                "chunk_count": len(rows),
                "refinement": refinement or "",
            }
        )

        return RetrievalResult(
            context_text="\n\n---\n\n".join(context_parts),
            citations=citations,
            warnings=warnings,
            metadata=meta,
        )
