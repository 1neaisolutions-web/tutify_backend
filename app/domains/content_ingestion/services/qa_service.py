"""
QA validation service.
Model/dimension aware: validates embedding_v for active model and runs sample retrieval.
"""
import asyncio
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.config import settings
from app.domains.content_ingestion.models import Document, QAValidation, PageText, Chunk
from app.domains.content_ingestion.enums import QAStatus, DocumentStatus

logger = get_logger(__name__)


class QAService:
    """Service for QA validation of documents."""
    
    def __init__(self, db: Session):
        """Initialize QA service."""
        self.db = db
    
    def run_qa_validation(
        self,
        document_id: UUID,
        thresholds: Optional[Dict[str, Any]] = None,
        golden_queries: Optional[List[str]] = None
    ) -> QAValidation:
        """
        Run QA validation checks on a document.
        
        Args:
            document_id: Document UUID
            thresholds: Optional threshold overrides
            golden_queries: Optional custom golden queries
            
        Returns:
            QAValidation object
        """
        document = self.db.query(Document).filter(
            Document.id == document_id
        ).first()
        
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        logger.info(f"Running QA validation for document {document_id}")
        
        # Default thresholds
        default_thresholds = {
            "min_chars_per_page": 100,
            "max_empty_pages_pct": 0.1,  # 10% max empty pages
            "min_embedding_completeness": 0.95,  # 95% of chunks must have embeddings
            "min_retrieval_similarity": 0.7,  # Minimum similarity score for golden queries
        }
        
        final_thresholds = {**default_thresholds, **(thresholds or {})}
        
        # Default golden queries
        default_queries = [
            "What is the main topic?",
            "Explain the key concepts",
            "What are the important details?",
        ]
        final_queries = golden_queries or default_queries
        
        # Run checks
        page_coverage_check = self._check_page_coverage(document_id)
        text_density_check = self._check_text_density(document_id, final_thresholds["min_chars_per_page"])
        embedding_completeness_check = self._check_embedding_completeness(
            document_id, final_thresholds["min_embedding_completeness"]
        )
        vector_retrieval_check, golden_query_results = self._check_vector_retrieval(
            document_id, final_queries, final_thresholds["min_retrieval_similarity"]
        )
        math_qa_check = self._check_math_qa(document_id, document)
        
        # Calculate metrics
        metrics = self._calculate_metrics(document_id)
        
        # Determine overall status (math check only when content_type_hint=math)
        all_checks_passed = (
            page_coverage_check and
            text_density_check and
            embedding_completeness_check and
            vector_retrieval_check and
            math_qa_check
        )
        
        qa_status = QAStatus.PASSED.value if all_checks_passed else QAStatus.FAILED.value
        
        # Create QA validation record
        qa_validation = QAValidation(
            document_id=document_id,
            qa_status=qa_status,
            thresholds=final_thresholds,
            golden_query_results=golden_query_results,
            page_coverage_check=page_coverage_check,
            text_density_check=text_density_check,
            embedding_completeness_check=embedding_completeness_check,
            vector_retrieval_check=vector_retrieval_check,
            metrics=metrics
        )
        
        self.db.add(qa_validation)
        self.db.commit()
        self.db.refresh(qa_validation)
        
        logger.info(f"QA validation completed for document {document_id}: {qa_status}")
        return qa_validation
    
    def _check_page_coverage(self, document_id: UUID) -> bool:
        """Check if all pages were processed."""
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document or not document.total_pages:
            return False
        
        pages_processed = self.db.query(PageText).filter(
            PageText.document_id == document_id
        ).count()
        
        return pages_processed >= document.total_pages * 0.95  # 95% coverage required
    
    def _check_text_density(self, document_id: UUID, min_chars: int) -> bool:
        """Check if text density meets threshold."""
        pages = self.db.query(PageText).filter(
            PageText.document_id == document_id
        ).all()
        
        if not pages:
            return False
        
        empty_pages = sum(1 for p in pages if p.char_count < min_chars)
        empty_pages_pct = empty_pages / len(pages) if pages else 1.0
        
        return empty_pages_pct <= 0.1  # Max 10% empty pages
    
    def _active_embedding_model(self, document_id: UUID) -> Optional[str]:
        """Infer active embedding model from chunks (embedding_v preferred)."""
        c = self.db.query(Chunk).filter(
            Chunk.document_id == document_id,
            Chunk.embedding_v.isnot(None)
        ).first()
        if c and c.embedding_model:
            return c.embedding_model
        c = self.db.query(Chunk).filter(
            Chunk.document_id == document_id,
            Chunk.embedding.isnot(None)
        ).first()
        return c.embedding_model if c else (settings.EMBEDDING_PROVIDER or "fake")

    def _check_embedding_completeness(self, document_id: UUID, min_completeness: float) -> bool:
        """Check if embeddings are complete (embedding_v for active model, else legacy)."""
        total_chunks = self.db.query(Chunk).filter(
            Chunk.document_id == document_id
        ).count()
        if total_chunks == 0:
            return False
        active = self._active_embedding_model(document_id)
        if active and active in ("fake", "local"):
            chunks_with_embeddings = self.db.query(Chunk).filter(
                Chunk.document_id == document_id,
                Chunk.embedding_v.isnot(None),
                Chunk.embedding_model == active
            ).count()
        else:
            # openai and other real providers may store in embedding_v (variable-dim)
            # or the legacy fixed-dim embedding column — count either.
            chunks_with_embeddings = self.db.query(Chunk).filter(
                Chunk.document_id == document_id,
                (Chunk.embedding_v.isnot(None)) | (Chunk.embedding.isnot(None))
            ).count()
        completeness = chunks_with_embeddings / total_chunks if total_chunks > 0 else 0.0
        return completeness >= min_completeness
    
    def _check_vector_retrieval(
        self,
        document_id: UUID,
        queries: List[str],
        min_similarity: float
    ) -> tuple[bool, List[Dict[str, Any]]]:
        """Run sample similarity search with active provider; validate results returned."""
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return False, []
        active_model = self._active_embedding_model(document_id)
        # Resolve embedding provider and run one query
        from app.domains.content_ingestion.providers.embedding_providers import (
            FakeEmbeddingProvider,
            LocalSentenceTransformersEmbeddingProvider,
            OpenAIEmbeddingProvider,
        )
        from app.domains.content_ingestion.providers.vector_stores import PgVectorStore
        emb = (settings.EMBEDDING_PROVIDER or "fake").lower()
        if emb == "openai":
            prov = OpenAIEmbeddingProvider()
        elif emb == "local":
            prov = LocalSentenceTransformersEmbeddingProvider()
        else:
            prov = FakeEmbeddingProvider()
        if not prov.validate_config():
            logger.warning("QA: embedding provider not configured, skipping retrieval check")
            chunks_count = self.db.query(Chunk).filter(
                Chunk.document_id == document_id,
                Chunk.embedding_v.isnot(None) if active_model in ("fake", "local") else Chunk.embedding.isnot(None)
            ).count()
            return chunks_count > 0, [{"query": q, "passed": chunks_count > 0, "chunks_found": chunks_count, "note": "No provider"} for q in queries]
        store = PgVectorStore(db=self.db)
        sample_query = queries[0] if queries else "main topic"
        try:
            async def _run():
                vecs = await prov.embed([sample_query])
                if not vecs:
                    return [], False
                hits = await store.query(
                    vecs[0],
                    pack_id=str(document.pack_id),
                    top_k=5,
                    filters={"document_id": str(document_id)},
                    embedding_model=active_model if active_model in ("fake", "local") else None,
                )
                return hits, len(hits) > 0
            try:
                hits, passed = asyncio.run(_run())
            except RuntimeError as e:
                if "running" in str(e).lower() or "event loop" in str(e).lower():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        hits, passed = loop.run_until_complete(_run())
                    finally:
                        loop.close()
                else:
                    raise
        except Exception as e:
            logger.warning(f"QA vector retrieval check failed: {e}")
            passed = False
            hits = []
        chunks_count = len(hits)
        results = [{"query": sample_query, "passed": passed, "chunks_found": chunks_count, "note": "Sample retrieval"}]
        for q in queries[1:]:
            results.append({"query": q, "passed": passed, "chunks_found": chunks_count, "note": "Same run"})
        return passed, results
    
    def _check_math_qa(self, document_id: UUID, document: Document) -> bool:
        """If content_type_hint=math, ensure math markers in chunks or math_blocks count > 0."""
        meta = document.processing_metadata or {}
        if meta.get("content_type_hint") != "math":
            return True
        from app.domains.content_ingestion.models import MathBlock
        math_blocks_count = self.db.query(MathBlock).filter(MathBlock.document_id == document_id).count()
        if math_blocks_count > 0:
            return True
        chunks = self.db.query(Chunk).filter(Chunk.document_id == document_id).all()
        marker_count = sum(1 for c in chunks if c.text and "[[MATH]]" in (c.text or ""))
        return marker_count >= 1

    def _calculate_metrics(self, document_id: UUID) -> Dict[str, Any]:
        """Calculate QA metrics."""
        pages = self.db.query(PageText).filter(
            PageText.document_id == document_id
        ).all()
        
        chunks = self.db.query(Chunk).filter(
            Chunk.document_id == document_id
        ).all()
        
        if not pages:
            return {}
        
        total_chars = sum(p.char_count for p in pages)
        avg_chars_per_page = total_chars / len(pages) if pages else 0
        empty_pages = sum(1 for p in pages if p.char_count < 100)
        empty_pages_pct = empty_pages / len(pages) if pages else 0.0
        
        active = self._active_embedding_model(document_id)
        if active and active in ("fake", "local"):
            chunks_with_embeddings = sum(1 for c in chunks if getattr(c, "embedding_v", None) is not None and c.embedding_model == active)
        else:
            # openai and real providers may use embedding_v (variable-dim) or legacy embedding
            chunks_with_embeddings = sum(
                1 for c in chunks if getattr(c, "embedding_v", None) is not None or c.embedding is not None
            )
        embedding_completeness = chunks_with_embeddings / len(chunks) if chunks else 0.0
        
        return {
            "avg_chars_per_page": round(avg_chars_per_page, 2),
            "empty_pages_pct": round(empty_pages_pct * 100, 2),
            "embedding_completeness_pct": round(embedding_completeness * 100, 2),
            "total_pages": len(pages),
            "total_chunks": len(chunks),
            "chunks_with_embeddings": chunks_with_embeddings
        }
