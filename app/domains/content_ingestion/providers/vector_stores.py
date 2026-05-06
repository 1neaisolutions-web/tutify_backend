"""
Vector store implementations.
"""
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text, func
from pgvector.sqlalchemy import Vector

from app.core.logging import get_logger
from app.domains.content_ingestion.providers.base import VectorStore, Chunk, VectorHit
from app.domains.content_ingestion.text_db import sanitize_pg_text
from app.db.session import SessionLocal

logger = get_logger(__name__)


class PgVectorStore(VectorStore):
    """PostgreSQL vector store using pgvector."""
    
    provider_name = "pgvector"
    
    def __init__(self, db: Optional[Session] = None):
        """Initialize pgvector store."""
        self.db = db
    
    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        return SessionLocal()
    
    def validate_config(self) -> bool:
        """Check if pgvector extension is enabled."""
        try:
            db = self._get_db()
            try:
                result = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                exists = result.scalar() is not None
                if not self.db:
                    db.close()
                return exists
            except Exception as e:
                if not self.db:
                    db.close()
                logger.warning(f"pgvector extension check failed: {e}")
                return False
        except Exception as e:
            logger.warning(f"Database connection failed: {e}")
            return False
    
    async def upsert(
        self,
        chunks: List[Chunk],
        vectors: List[List[float]],
        document_id: str,
        pack_id: str,
        embedding_model: Optional[str] = None,
        embedding_dim: Optional[int] = None,
        embedding_provider: Optional[str] = None,
        **kwargs
    ) -> int:
        """
        Upsert chunks with embeddings into pgvector.
        Writes into embedding_v, embedding_model, embedding_dim, embedding_provider.
        Legacy 'embedding' column is unchanged for backwards compatibility.
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"Chunks ({len(chunks)}) and vectors ({len(vectors)}) count mismatch")
        if not chunks:
            return 0
        dim = embedding_dim or len(vectors[0])
        for i, v in enumerate(vectors):
            if len(v) != dim:
                raise ValueError(
                    f"Vector at index {i} has length {len(v)}, expected {dim}. "
                    "All vectors must have the same dimension."
                )

        db = self._get_db()
        try:
            from app.domains.content_ingestion.models import Chunk as ChunkModel
            import hashlib

            PGVECTOR_DIM = 1536
            stored_count = 0
            for chunk, vector in zip(chunks, vectors):
                try:
                    chunk.text = sanitize_pg_text(chunk.text)
                    chunk_hash = hashlib.sha256(chunk.text.encode()).hexdigest()
                    # Pad vector to PGVECTOR_DIM for storage (embedding_v column is vector(1536))
                    vec_padded = list(vector) + [0.0] * (PGVECTOR_DIM - len(vector)) if len(vector) < PGVECTOR_DIM else list(vector)[:PGVECTOR_DIM]

                    existing = db.query(ChunkModel).filter(
                        ChunkModel.document_id == UUID(document_id),
                        ChunkModel.chunk_id == chunk.chunk_id
                    ).first()

                    if existing:
                        existing.text = chunk.text
                        existing.page_start_pdf = chunk.page_start
                        existing.page_end_pdf = chunk.page_end
                        existing.topic_id = chunk.topic_id
                        existing.topic_title = chunk.topic_title
                        existing.embedding_v = vec_padded
                        existing.embedding_model = embedding_model
                        existing.embedding_dim = dim
                        existing.embedding_provider = embedding_provider
                        existing.metadata_json = chunk.metadata
                        existing.chunk_hash = chunk_hash
                    else:
                        chunk_model = ChunkModel(
                            document_id=UUID(document_id),
                            chunk_id=chunk.chunk_id,
                            chunk_hash=chunk_hash,
                            text=chunk.text,
                            page_start_pdf=chunk.page_start,
                            page_end_pdf=chunk.page_end,
                            topic_id=chunk.topic_id,
                            topic_title=chunk.topic_title,
                            embedding_v=vec_padded,
                            embedding_model=embedding_model,
                            embedding_dim=dim,
                            embedding_provider=embedding_provider,
                            metadata_json=chunk.metadata
                        )
                        db.add(chunk_model)
                    stored_count += 1
                except Exception as e:
                    logger.error(f"Error storing chunk {chunk.chunk_id}: {e}")
                    raise

            # CRITICAL: Flush before verification so ORM queries see uncommitted rows
            db.flush()

            # Post-upsert verification after flush
            verify_count = db.query(ChunkModel).filter(
                ChunkModel.document_id == UUID(document_id),
                ChunkModel.embedding_v.isnot(None),
                ChunkModel.embedding_model == embedding_model
            ).count()

            if verify_count == 0:
                db.rollback()
                raise RuntimeError(
                    f"Post-upsert verification failed: 0 chunks with embedding_v found for document_id={document_id}, "
                    f"embedding_model={embedding_model}. Embeddings were not persisted."
                )
            db.commit()
            logger.info(f"Stored {stored_count}/{len(chunks)} chunks in pgvector (verified {verify_count})")
            return stored_count
        except Exception as e:
            db.rollback()
            logger.error(f"pgvector upsert failed: {e}")
            raise RuntimeError(f"Vector store upsert failed: {str(e)}")
        finally:
            if not self.db:
                db.close()
    
    async def query(
        self,
        query_vector: List[float],
        pack_id: str,
        top_k: int = 10,
        topic_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        embedding_model: Optional[str] = None,
        pack_ids: Optional[List[str]] = None,
        **kwargs
    ) -> List[VectorHit]:
        """
        Query pgvector for similar chunks.
        If embedding_model is specified, use embedding_v column; else legacy embedding.
        pack_id: single pack (backward compat). pack_ids: optional list for multi-pack search.
        filters["roles"]: optional list of role strings (concept, worked_example, etc.).
        """
        db = self._get_db()
        try:
            from app.domains.content_ingestion.models import Chunk as ChunkModel, Document

            PGVECTOR_DIM = 1536
            vec = list(query_vector)
            if len(vec) < PGVECTOR_DIM:
                vec = vec + [0.0] * (PGVECTOR_DIM - len(vec))
            else:
                vec = vec[:PGVECTOR_DIM]
            vector_str = '[' + ','.join(str(float(x)) for x in vec) + ']'

            # Route: embedding_model specified -> use embedding_v; else legacy embedding
            if embedding_model:
                vec_column = "chunks.embedding_v"
                where_vec = "chunks.embedding_v IS NOT NULL AND chunks.embedding_model = :embedding_model"
                params_extra = {"embedding_model": embedding_model}
            else:
                vec_column = "chunks.embedding"
                where_vec = "chunks.embedding IS NOT NULL"
                params_extra = {}

            # Pack filter: multi-pack (pack_ids) or single pack_id
            if pack_ids and len(pack_ids) > 0:
                where_conditions = [
                    "documents.pack_id = ANY(:pack_ids)",
                    "documents.status = 'published'",
                    where_vec,
                ]
                params = {"pack_ids": pack_ids, "top_k": top_k, **params_extra}
            else:
                where_conditions = [
                    "documents.pack_id = :pack_id",
                    "documents.status = 'published'",
                    where_vec,
                ]
                params = {"pack_id": str(pack_id), "top_k": top_k, **params_extra}

            if topic_id:
                where_conditions.append("chunks.topic_id = :topic_id")
                params["topic_id"] = topic_id
            if filters and "document_id" in filters:
                where_conditions.append("chunks.document_id = :document_id")
                params["document_id"] = str(filters["document_id"])
            if filters and "min_page" in filters:
                where_conditions.append("chunks.page_start_pdf > :min_page")
                params["min_page"] = int(filters["min_page"])
            if filters and "max_page" in filters:
                where_conditions.append("chunks.page_start_pdf <= :max_page")
                params["max_page"] = int(filters["max_page"])
            if filters and "roles" in filters and filters["roles"]:
                where_conditions.append("chunks.metadata_json->>'role' = ANY(:roles)")
                params["roles"] = list(filters["roles"])

            where_clause = " AND ".join(where_conditions)
            results_with_distance = db.execute(
                text(f"""
                    SELECT 
                        chunks.id,
                        chunks.document_id,
                        chunks.chunk_id,
                        chunks.text,
                        chunks.page_start_pdf,
                        chunks.page_end_pdf,
                        documents.pack_id,
                        {vec_column},
                        chunks.metadata_json,
                        {vec_column} <=> '{vector_str}'::vector as distance
                    FROM chunks
                    JOIN documents ON chunks.document_id = documents.id
                    WHERE {where_clause}
                    ORDER BY {vec_column} <=> '{vector_str}'::vector
                    LIMIT :top_k
                """),
                params
            ).fetchall()
            
            hits = []
            for row in results_with_distance:
                distance = float(row.distance) if row.distance is not None else 2.0
                similarity = max(0.0, 1.0 - (distance / 2.0))
                meta = dict(row.metadata_json or {})
                if getattr(row, "page_start_pdf", None) is not None:
                    meta["page_start_pdf"] = row.page_start_pdf
                if getattr(row, "page_end_pdf", None) is not None:
                    meta["page_end_pdf"] = row.page_end_pdf
                if getattr(row, "pack_id", None) is not None:
                    meta["pack_id"] = str(row.pack_id)
                hits.append(VectorHit(
                    chunk_id=row.chunk_id,
                    document_id=str(row.document_id),
                    text=row.text,
                    similarity_score=similarity,
                    metadata=meta if meta else None
                ))
            
            log_pack = pack_ids if pack_ids else pack_id
            logger.info(f"Query returned {len(hits)} results for pack(s) {log_pack}")
            return hits
            
        except Exception as e:
            logger.error(f"pgvector query failed: {e}")
            raise RuntimeError(f"Vector store query failed: {str(e)}")
        finally:
            if not self.db:
                db.close()
    
    async def delete_document(
        self,
        document_id: str,
        **kwargs
    ) -> bool:
        """
        Delete all chunks for a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            True if successful
        """
        db = self._get_db()
        try:
            from app.domains.content_ingestion.models import Chunk as ChunkModel
            
            deleted = db.query(ChunkModel).filter(
                ChunkModel.document_id == UUID(document_id)
            ).delete()
            
            db.commit()
            logger.info(f"Deleted {deleted} chunks for document {document_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete chunks for document {document_id}: {e}")
            return False
        finally:
            if not self.db:
                db.close()
