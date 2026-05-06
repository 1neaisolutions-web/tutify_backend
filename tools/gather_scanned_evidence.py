"""Gather evidence for scanned PDF."""
import os
import sys
from pathlib import Path

os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["FAKE_EMBEDDING_DIM"] = "384"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document
from app.domains.content_ingestion.providers.embedding_providers import FakeEmbeddingProvider
import asyncio

async def gather_scanned_evidence():
    """Gather evidence for scanned PDF."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.filename == "math_ocr_test_pack_scanned.pdf").order_by(Document.created_at.desc()).first()
        if not doc:
            print("Scanned PDF not found")
            return
        
        doc_id = str(doc.id)
        print(f"Document ID: {doc_id}")
        print(f"Status: {doc.status}")
        print(f"OCR Ran: {'Yes' if doc.processing_metadata and doc.processing_metadata.get('ocr_attempted') else 'No'}")
        
        # Page texts
        page_result = db.execute(
            text("""
                SELECT 
                    COUNT(*) AS pages,
                    SUM(CASE WHEN char_count > 0 THEN 1 ELSE 0 END) AS non_empty_pages
                FROM page_texts
                WHERE document_id = :d
            """),
            {"d": doc_id},
        ).fetchone()
        
        print(f"\nPage texts: {page_result[0] or 0} total, {page_result[1] or 0} non-empty")
        
        # Chunks
        total_chunks = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE document_id = :d"),
            {"d": doc_id},
        ).scalar_one()
        
        chunks_with_vectors = db.execute(
            text("""
                SELECT COUNT(*) 
                FROM chunks 
                WHERE document_id = :d 
                  AND embedding_v IS NOT NULL 
                  AND embedding_model = 'fake'
            """),
            {"d": doc_id},
        ).scalar_one()
        
        print(f"Chunks: {total_chunks} total, {chunks_with_vectors} with embedding_v")
        
        # Model info
        model_info = db.execute(
            text("""
                SELECT embedding_model, embedding_dim, embedding_provider, COUNT(*)
                FROM chunks
                WHERE document_id = :d
                GROUP BY embedding_model, embedding_dim, embedding_provider
            """),
            {"d": doc_id},
        ).fetchall()
        
        print("\nModel/Dim/Provider:")
        for row in model_info:
            print(f"  {row[0]}, dim={row[1]}, provider={row[2]}, count={row[3]}")
        
        # Math blocks
        try:
            math_blocks = db.execute(
                text("SELECT COUNT(*) FROM math_blocks WHERE document_id = :d"),
                {"d": doc_id},
            ).scalar_one()
            print(f"\nMath blocks: {math_blocks}")
        except:
            print("\nMath blocks: N/A")
        
        chunks_with_math = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE document_id = :d AND text LIKE '%[[MATH]]%'"),
            {"d": doc_id},
        ).scalar_one()
        print(f"Chunks with [[MATH]]: {chunks_with_math}")
        
        # Retrieval
        print("\nRetrieval test:")
        emb_provider = FakeEmbeddingProvider()
        query_text = "solve linear equation"
        query_vec = (await emb_provider.embed([query_text]))[0]
        provider_dim = len(query_vec)
        
        PGVECTOR_DIM = 1536
        q_vec_padded = list(query_vec) + [0.0] * (PGVECTOR_DIM - provider_dim)
        vector_str = "[" + ",".join(str(float(x)) for x in q_vec_padded) + "]"
        
        results = db.execute(
            text(f"""
                SELECT 
                    chunk_id, 
                    page_start_pdf, 
                    page_end_pdf,
                    (embedding_v <=> '{vector_str}'::vector) AS distance,
                    LEFT(text, 120) AS snippet
                FROM chunks
                WHERE document_id = :d
                  AND embedding_v IS NOT NULL
                  AND embedding_model = 'fake'
                ORDER BY embedding_v <=> '{vector_str}'::vector
                LIMIT 5
            """),
            {"d": doc_id},
        ).fetchall()
        
        print(f"Query: '{query_text}'")
        for i, row in enumerate(results, 1):
            print(f"  {i}. chunk_id={row[0]}, distance={row[3]:.4f}, pages={row[1]}-{row[2]}")
            print(f"     snippet: {row[4][:80]}...")
            
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(gather_scanned_evidence())
