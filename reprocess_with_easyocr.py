"""Reprocess document with EasyOCR enabled."""
import os
import sys
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk, DocumentProcessingRun
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.jobs import run_ingestion_job_sync
from uuid import UUID

# Set OCR_ENGINE to easyocr
os.environ['OCR_ENGINE'] = 'easyocr'

PACK_ID = "67ff7e11-a2e7-4eac-9177-9f682fb3ba0e"

print("=" * 70)
print("REPROCESSING DOCUMENT WITH EASYOCR")
print("=" * 70)
print()
print(f"OCR_ENGINE set to: {os.environ.get('OCR_ENGINE', 'tesseract')}")
print()

db: Session = SessionLocal()
try:
    pack_uuid = UUID(PACK_ID)
    documents = db.query(Document).filter(Document.pack_id == pack_uuid).all()
    
    if not documents:
        print("No documents found in pack")
        sys.exit(1)
    
    for doc in documents:
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        
        print(f"Document: {doc.filename}")
        print(f"  Status: {doc.status}")
        print(f"  Chunks with embeddings: {chunks_with_emb}")
        
        # Reprocess if no embeddings
        if chunks_with_emb == 0:
            print(f"  🔄 Reprocessing with EasyOCR...")
            try:
                # Reset status to uploaded to allow reprocessing
                doc.status = DocumentStatus.UPLOADED.value
                doc.error_code = None
                doc.error_message = None
                doc.remediation_hint = None
                db.commit()
                
                # Trigger ingestion job
                print(f"  ⏳ Running ingestion pipeline...")
                run_ingestion_job_sync(doc.id)
                
                # Check status
                db.refresh(doc)
                print(f"  ✅ Processing completed")
                print(f"  New status: {doc.status}")
                
                # Check chunks again
                chunks_with_emb_after = db.query(Chunk).filter(
                    Chunk.document_id == doc.id,
                    Chunk.embedding.isnot(None)
                ).count()
                print(f"  Chunks with embeddings after: {chunks_with_emb_after}")
                
            except Exception as e:
                print(f"  ❌ Reprocessing failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"  ✅ Document already has embeddings")
        
        print()
        
finally:
    db.close()

print("=" * 70)
print("REPROCESSING COMPLETE")
print("=" * 70)
