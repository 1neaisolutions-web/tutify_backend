"""
Re-chunk a document from stored page_texts (no re-OCR).

Optionally auto-extracts level-2 section headings into chapter_map, re-embeds,
and rebuilds document_topics.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.content_ingestion.document_topics_service import populate_document_topics
from app.domains.content_ingestion.models import Chunk, Document, DocumentTopic, PageText
from app.domains.content_ingestion.providers.base import PageText as ChunkPageText
from app.domains.content_ingestion.providers.chunkers import SimpleChunker, validate_topic_assignment
from app.domains.content_ingestion.providers.embedding_providers import (
    FakeEmbeddingProvider,
    LocalSentenceTransformersEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from app.domains.content_ingestion.providers.vector_stores import PgVectorStore
from app.domains.content_ingestion.section_heading_extractor import merge_sections_into_chapter_map

logger = get_logger(__name__)


@dataclass
class RechunkReport:
    document_id: uuid.UUID
    chunks_created: int = 0
    sections_added: int = 0
    coverage: float = 0.0
    mislabeled_count: int = 0
    chapters_with_zero_chunks: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "chunks_created": self.chunks_created,
            "sections_added": self.sections_added,
            "coverage": self.coverage,
            "mislabeled_count": self.mislabeled_count,
            "chapters_with_zero_chunks": self.chapters_with_zero_chunks,
            "errors": self.errors,
        }


def _count_mislabeled_chunks(db: Session, document_id: uuid.UUID) -> int:
    rows = (
        db.query(Chunk)
        .join(DocumentTopic, Chunk.topic_fk == DocumentTopic.id)
        .filter(
            Chunk.document_id == document_id,
            Chunk.page_start_pdf.isnot(None),
            DocumentTopic.start_page_pdf.isnot(None),
            Chunk.page_start_pdf < DocumentTopic.start_page_pdf,
        )
        .count()
    )
    return int(rows or 0)


def _embedding_provider_for_document(document: Document):
    provider_name = getattr(settings, "EMBEDDING_PROVIDER", "fake")
    if provider_name == "openai":
        return OpenAIEmbeddingProvider()
    if provider_name == "local":
        return LocalSentenceTransformersEmbeddingProvider()
    return FakeEmbeddingProvider()


def _maybe_enrich_chapter_map(document: Document, pages: List[tuple[int, str]]) -> int:
    chapter_map = list(document.chapter_map or [])
    if not chapter_map:
        return 0
    if not getattr(settings, "AUTO_EXTRACT_SECTION_TOC", True):
        return 0
    has_level2 = any(int(e.get("level") or 1) > 1 for e in chapter_map)
    if has_level2:
        return 0
    enriched = merge_sections_into_chapter_map(chapter_map, pages)
    added = len(enriched) - len(chapter_map)
    if added > 0:
        document.chapter_map = enriched
    return added


class RechunkService:
    def __init__(self, db: Session):
        self.db = db
        self.chunker = SimpleChunker()
        self.vector_store = PgVectorStore(db=db)

    async def rechunk_document(self, document_id: uuid.UUID) -> RechunkReport:
        report = RechunkReport(document_id=document_id)
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            report.errors.append("Document not found")
            return report

        page_rows = (
            self.db.query(PageText)
            .filter(PageText.document_id == document_id)
            .order_by(PageText.page_no.asc())
            .all()
        )
        if not page_rows:
            report.errors.append("No page_texts stored; re-upload or re-OCR required")
            return report

        pages_tuple = [(p.page_no, p.text or "") for p in page_rows]
        # Rechunk always rebuilds sections from level-1 TOC to avoid stale/duplicate section rows.
        level1_only = [
            e for e in (document.chapter_map or []) if int(e.get("level") or 1) == 1
        ]
        document.chapter_map = level1_only
        report.sections_added = _maybe_enrich_chapter_map(document, pages_tuple)
        if report.sections_added:
            meta = dict(document.processing_metadata or {})
            meta["sections_auto_extracted"] = report.sections_added
            meta["toc_source"] = meta.get("toc_source", "chapter_map") + "+auto_sections"
            document.processing_metadata = meta
            self.db.commit()

        normalized_pages = [
            ChunkPageText(page_no=p.page_no, text=p.text or "", char_count=p.char_count or len(p.text or ""))
            for p in page_rows
        ]

        meta_chunk = dict(document.processing_metadata or {})
        ocr_used = bool(meta_chunk.get("ocr_used"))
        chunk_size = settings.CHUNK_SIZE_TOKENS_OCR if ocr_used else settings.CHUNK_SIZE_TOKENS_DIGITAL
        overlap = settings.CHUNK_OVERLAP_TOKENS_OCR if ocr_used else settings.CHUNK_OVERLAP_TOKENS_DIGITAL

        chunks = self.chunker.chunk(
            normalized_pages,
            chunk_size_tokens=chunk_size,
            overlap_tokens=overlap,
            chapter_map=document.chapter_map,
        )
        chunks = [c for c in chunks if (c.text or "").strip()]
        report.chunks_created = len(chunks)

        if not chunks:
            report.errors.append("Chunking produced zero non-empty chunks")
            return report

        validate_topic_assignment(chunks, document.chapter_map)

        embedder = _embedding_provider_for_document(document)
        chunk_texts = [c.text for c in chunks]
        try:
            embeddings = await embedder.embed(chunk_texts)
        except RuntimeError as embed_err:
            low = str(embed_err).lower()
            if "403" not in low and "quota" not in low and "429" not in low:
                report.errors.append(str(embed_err))
                return report
            logger.warning(
                "rechunk_embedding_fallback_fake",
                extra={"document_id": str(document_id), "error": str(embed_err)},
            )
            embedder = FakeEmbeddingProvider()
            embeddings = await embedder.embed(chunk_texts)
        if len(embeddings) != len(chunks):
            report.errors.append(f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}")
            return report

        await self.vector_store.delete_document(str(document_id))

        batch_size = 100
        stored_total = 0
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            batch_chunks = chunks[start:end]
            batch_vectors = embeddings[start:end]
            stored = await self.vector_store.upsert(
                chunks=batch_chunks,
                vectors=batch_vectors,
                document_id=str(document_id),
                pack_id=str(document.pack_id),
                embedding_model=getattr(embedder, "embedding_model", None) or embedder.provider_name,
                embedding_dim=embedder.get_embedding_dimension(),
                embedding_provider=embedder.provider_name,
            )
            stored_total += stored
        logger.info(
            "rechunk_stored",
            extra={"document_id": str(document_id), "stored": stored_total, "total": len(chunks)},
        )

        topic_report = populate_document_topics(self.db, document, replace_existing=True)
        report.coverage = topic_report.coverage
        report.chapters_with_zero_chunks = list(topic_report.chapters_with_zero_chunks)
        report.mislabeled_count = _count_mislabeled_chunks(self.db, document_id)

        meta = dict(document.processing_metadata or {})
        meta["rechunk_summary"] = {
            "chunks_created": report.chunks_created,
            "sections_added": report.sections_added,
            "coverage": report.coverage,
            "mislabeled_count": report.mislabeled_count,
        }
        document.processing_metadata = meta
        self.db.commit()
        return report
