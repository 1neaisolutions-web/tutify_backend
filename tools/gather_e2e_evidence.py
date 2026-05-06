"""
Gather DB evidence for E2E test documents.
"""
import os
import sys
from pathlib import Path

# Set FREE MODE env vars BEFORE any imports
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["FAKE_EMBEDDING_DIM"] = "384"
os.environ["VECTOR_STORE"] = "pgvector"
os.environ["OCR_PROVIDER"] = "tesseract"

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document
from app.domains.content_ingestion.providers.embedding_providers import FakeEmbeddingProvider
import asyncio

async def gather_evidence_for_document(db: Session, document_id: str, pdf_name: str):
    """Gather all evidence for a document."""
    print(f"\n{'='*80}")
    print(f"EVIDENCE FOR: {pdf_name}")
    print(f"Document ID: {document_id}")
    print(f"{'='*80}\n")
    
    # Get document status
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        print(f"[FAIL] Document {document_id} not found")
        return
    
    print(f"Final Status: {doc.status}")
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
        {"d": document_id},
    ).fetchone()
    
    print(f"\n[PAGE TEXTS]")
    print(f"  Total pages: {page_result[0] or 0}")
    print(f"  Non-empty pages: {page_result[1] or 0}")
    
    # Chunks
    total_chunks = db.execute(
        text("SELECT COUNT(*) FROM chunks WHERE document_id = :d"),
        {"d": document_id},
    ).scalar_one()
    
    chunks_with_vectors = db.execute(
        text("""
            SELECT COUNT(*) 
            FROM chunks 
            WHERE document_id = :d 
              AND embedding_v IS NOT NULL 
              AND embedding_model = 'fake'
        """),
        {"d": document_id},
    ).scalar_one()
    
    print(f"\n[CHUNKS]")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Chunks with embedding_v (model='fake'): {chunks_with_vectors}")
    
    # Model/dim/provider breakdown
    model_info = db.execute(
        text("""
            SELECT embedding_model, embedding_dim, embedding_provider, COUNT(*)
            FROM chunks
            WHERE document_id = :d
            GROUP BY embedding_model, embedding_dim, embedding_provider
        """),
        {"d": document_id},
    ).fetchall()
    
    print(f"\n[MODEL/DIM/PROVIDER]")
    for row in model_info:
        print(f"  model={row[0]}, dim={row[1]}, provider={row[2]}, count={row[3]}")
    
    # Math blocks
    try:
        math_blocks_count = db.execute(
            text("SELECT COUNT(*) FROM math_blocks WHERE document_id = :d"),
            {"d": document_id},
        ).scalar_one()
        print(f"\n[MATH BLOCKS]")
        print(f"  Total math blocks: {math_blocks_count}")
    except Exception:
        print(f"\n[MATH BLOCKS]")
        print(f"  Table not available or error querying")
    
    chunks_with_math = db.execute(
        text("""
            SELECT COUNT(*) 
            FROM chunks 
            WHERE document_id = :d 
              AND text LIKE '%[[MATH]]%'
        """),
        {"d": document_id},
    ).scalar_one()
    
    print(f"  Chunks with [[MATH]] markers: {chunks_with_math}")
    
    # Retrieval test
    print(f"\n[RETRIEVAL TEST]")
    emb_provider = FakeEmbeddingProvider()
    query_text = "solve linear equation"
    query_vec = (await emb_provider.embed([query_text]))[0]
    provider_dim = len(query_vec)
    
    # Pad to 1536 for pgvector column
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
        {"d": document_id},
    ).fetchall()
    
    print(f"  Query: '{query_text}'")
    print(f"  Top 5 results:")
    for i, row in enumerate(results, 1):
        print(f"    {i}. chunk_id={row[0]}, distance={row[3]:.4f}, pages={row[1]}-{row[2]}")
        print(f"       snippet: {row[4][:100]}...")


async def main():
    """Main function."""
    db = SessionLocal()
    try:
        # Find documents by filename
        hybrid_doc = db.query(Document).filter(Document.filename == "math_ocr_test_pack.pdf").order_by(Document.created_at.desc()).first()
        scanned_doc = db.query(Document).filter(Document.filename == "math_ocr_test_pack_scanned.pdf").order_by(Document.created_at.desc()).first()
        
        if hybrid_doc:
            await gather_evidence_for_document(db, str(hybrid_doc.id), "math_ocr_test_pack.pdf")
        else:
            print("[WARN] Hybrid PDF document not found")
        
        if scanned_doc:
            await gather_evidence_for_document(db, str(scanned_doc.id), "math_ocr_test_pack_scanned.pdf")
        else:
            print("[WARN] Scanned PDF document not found")
            
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
