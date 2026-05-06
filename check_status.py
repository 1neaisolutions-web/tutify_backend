"""
Quick status check for document processing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk
from uuid import UUID

DOCUMENT_ID = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"

db = SessionLocal()
try:
    doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
    if doc:
        chunks_total = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        
        print(f"Status: {doc.status}")
        print(f"Pages: {doc.total_pages or 0}")
        print(f"Chunks: {chunks_total} total, {chunks_with_emb} with embeddings")
        print(f"Error: {doc.error_message or 'None'}")
        
        if doc.status == 'published' and chunks_with_emb > 0:
            print("\n[PASS] Document ready for worksheet generation!")
        elif doc.status == 'failed':
            print(f"\n[FAIL] Processing failed: {doc.error_message}")
        elif chunks_with_emb == 0:
            print("\n[WARN] No chunks with embeddings found")
    else:
        print("Document not found")
finally:
    db.close()
