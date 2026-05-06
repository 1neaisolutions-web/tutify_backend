"""Check document processing status."""
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk, DocumentProcessingRun
from uuid import UUID

DOCUMENT_ID = "05086659-475c-4755-a2d0-59bebbc3440c"

print("=" * 70)
print("DOCUMENT PROCESSING STATUS")
print("=" * 70)
print()

db: Session = SessionLocal()
try:
    doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
    if doc:
        print(f"Document: {doc.filename}")
        print(f"Status: {doc.status}")
        print(f"Error: {doc.error_message or 'None'}")
        print()
        
        # Get latest processing run
        latest_run = db.query(DocumentProcessingRun).filter(
            DocumentProcessingRun.document_id == doc.id
        ).order_by(DocumentProcessingRun.started_at.desc()).first()
        
        if latest_run:
            print(f"Processing Run:")
            print(f"  Status: {latest_run.status}")
            print(f"  Current Step: {latest_run.current_step}")
            print(f"  Progress: {latest_run.progress_percentage}%")
            print(f"  Pages Processed: {latest_run.pages_processed}")
            print(f"  Chunks Created: {latest_run.chunks_created}")
            print(f"  Vectors Stored: {latest_run.vectors_stored}")
            print(f"  Error: {latest_run.error_message or 'None'}")
        
        # Check chunks
        chunks_count = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        
        print()
        print(f"Chunks: {chunks_count} total, {chunks_with_emb} with embeddings")
        
finally:
    db.close()

print()
print("=" * 70)
