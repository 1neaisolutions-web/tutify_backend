from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.content_ingestion.models import ContentPack, DocumentTopic
from app.domains.content_ingestion.scope_query import (
    count_scoped_chunks_diagnostics,
    fetch_scoped_chunks,
)
from app.domains.content_ingestion.topic_scope import RetrievalScopeError


@dataclass(frozen=True)
class RetrievalResult:
    context_text: str
    citations: List[Dict[str, str]]
    warnings: List[str]
    metadata: Dict[str, Any]
    chunk_texts: Dict[str, str]


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
        seed: Optional[str] = None,
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
                chunk_texts={},
            )

        strict = bool(getattr(settings, "QUIZ_STRICT_SCOPE_ONLY", True))
        use_topic_ids = bool(
            scope_topic_ids
            and (settings.SCOPE_BY_TOPIC_ID_ENABLED or strict)
        )

        if strict and not generate_without_sources and not scope_topic_ids:
            raise RetrievalScopeError(
                "Select at least one chapter or topic before generating.",
                topic_ids=[],
                fallback_available=False,
            )

        if refinement and refinement.strip() and settings.EMBEDDING_PROVIDER == "fake":
            warnings.append("Semantic search unavailable; using text search instead.")

        if use_topic_ids and scope_topic_ids and getattr(settings, "SCOPE_PAGE_RANGE_GUARD_ENABLED", False):
            meta.update(
                count_scoped_chunks_diagnostics(
                    self.db,
                    tenant_id=tenant_id,
                    pack_ids=valid_pack_ids,
                    topic_ids=scope_topic_ids,
                    include_sub_topics=include_sub_topics,
                    refinement=refinement,
                )
            )

        rows, scope = fetch_scoped_chunks(
            self.db,
            tenant_id=tenant_id,
            pack_ids=valid_pack_ids,
            topic_ids=scope_topic_ids if use_topic_ids else None,
            topic_strings=topics if not use_topic_ids and not strict else None,
            include_sub_topics=include_sub_topics,
            refinement=refinement,
            limit=max_chunks,
            stratified=True,
            seed=seed,
        )

        applied_topic = scope.applied_topic_filter
        resolved_ids = scope.resolved_topic_ids

        if not rows and applied_topic:
            raise RetrievalScopeError(
                "No content found for selected chapters. The book may need re-processing.",
                topic_ids=scope_topic_ids or [],
                fallback_available=generate_without_sources,
            )

        topic_titles: Dict[UUID, str] = {}
        if rows and any(r[0].topic_fk for r in rows):
            fk_ids = [r[0].topic_fk for r in rows if r[0].topic_fk]
            for dt in self.db.query(DocumentTopic).filter(DocumentTopic.id.in_(fk_ids)).all():
                topic_titles[dt.id] = dt.display_title

        citations: List[Dict[str, str]] = []
        context_parts: List[str] = []
        current_doc_header: Optional[str] = None
        chunk_ids: List[str] = []
        chunk_texts: Dict[str, str] = {}

        for chunk, doc, pack in rows:
            chunk_ids.append(str(chunk.id))
            chunk_texts[str(chunk.id)] = chunk.text or ""
            topic_label = topic_titles.get(chunk.topic_fk, chunk.topic_title or "")
            doc_header = f"=== {doc.title or doc.filename} (Pack: {pack.name}) ==="
            if doc_header != current_doc_header:
                context_parts.append(doc_header)
                current_doc_header = doc_header

            page_lo = chunk.page_start_pdf or "?"
            page_hi = chunk.page_end_pdf or page_lo
            section_header = (
                f"--- [chunk_id={chunk.id}] Chapter: {topic_label} | Pages {page_lo}–{page_hi} ---"
            )
            context_parts.append(section_header + "\n" + (chunk.text or ""))

            citations.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "pack_id": str(doc.pack_id),
                    "document_title": doc.title or doc.filename,
                    "topic_title": topic_label,
                    "topic_id": str(chunk.topic_fk) if chunk.topic_fk else "",
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
                "topic_ids": [str(x) for x in resolved_ids],
                "chunk_ids": chunk_ids,
                "chunk_count": len(rows),
                "refinement": refinement or "",
                "scope_mode": scope.scope_mode,
                "include_sub_topics": include_sub_topics,
            }
        )

        return RetrievalResult(
            context_text="\n\n".join(context_parts),
            citations=citations,
            warnings=warnings,
            metadata=meta,
            chunk_texts=chunk_texts,
        )
