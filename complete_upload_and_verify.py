"""
Complete upload and verification script for Mathematics PDF.
Ensures document is properly processed with chunks and embeddings before marking as published.
"""
import sys
import os
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.jobs import run_ingestion_job_sync
from uuid import UUID

# Set OCR to easyocr (free)
os.environ['OCR_ENGINE'] = 'easyocr'

DOCUMENT_ID = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"

def check_chunks(db, doc_id):
    """Check if document has chunks with embeddings."""
    chunks_total = db.query(Chunk).filter(Chunk.document_id == doc_id).count()
    chunks_with_emb = db.query(Chunk).filter(
        Chunk.document_id == doc_id,
        Chunk.embedding.isnot(None)
    ).count()
    return chunks_total, chunks_with_emb

def main():
    db = SessionLocal()
    try:
        print("="*70)
        print("COMPLETE DOCUMENT UPLOAD AND VERIFICATION")
        print("="*70)
        print()
        
        # Get document
        doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
        if not doc:
            print(f"[FAIL] Document {DOCUMENT_ID} not found!")
            return
        
        print(f"Document: {doc.filename}")
        print(f"Current Status: {doc.status}")
        print(f"Total Pages: {doc.total_pages or 0}")
        
        # Check current chunks
        chunks_total, chunks_with_emb = check_chunks(db, doc.id)
        print(f"Chunks: {chunks_total} total, {chunks_with_emb} with embeddings")
        print()
        
        # Reset if needed
        if doc.status == 'published' and chunks_with_emb == 0:
            print("[WARN] Document marked as published but has no chunks!")
            print("Resetting status to UPLOADED for reprocessing...")
            doc.status = DocumentStatus.UPLOADED.value
            doc.error_code = None
            doc.error_message = None
            doc.remediation_hint = None
            if not doc.processing_metadata:
                doc.processing_metadata = {}
            doc.processing_metadata['force_ocr'] = True
            db.commit()
            print("[PASS] Status reset successfully")
            print()
        
        # Process if not published or has no chunks
        if doc.status != 'published' or chunks_with_emb == 0:
            print("="*70)
            print("STARTING DOCUMENT PROCESSING")
            print("="*70)
            print()
            print("This will:")
            print("  1. Run OCR on 193 pages (EasyOCR - free)")
            print("  2. Extract and normalize text")
            print("  3. Create chunks")
            print("  4. Generate embeddings (OpenAI)")
            print("  5. Store in vector database")
            print("  6. Verify chunks are saved")
            print("  7. Run QA validation")
            print("  8. Publish only if chunks verified")
            print()
            print("Estimated time: 15-30 minutes for OCR processing")
            print()
            
            try:
                run_ingestion_job_sync(UUID(DOCUMENT_ID))
                print()
                print("[PASS] Processing completed!")
            except Exception as e:
                print()
                print(f"[FAIL] Processing failed: {e}")
                import traceback
                traceback.print_exc()
                return
        
        # Verify final status
        db.refresh(doc)
        chunks_total, chunks_with_emb = check_chunks(db, doc.id)
        
        print()
        print("="*70)
        print("FINAL VERIFICATION")
        print("="*70)
        print()
        print(f"Document Status: {doc.status}")
        print(f"Total Pages: {doc.total_pages or 0}")
        print(f"Chunks Total: {chunks_total}")
        print(f"Chunks with Embeddings: {chunks_with_emb}")
        print(f"Error: {doc.error_message or 'None'}")
        print()
        
        if doc.status == 'published' and chunks_with_emb > 0:
            print("[PASS] Document successfully processed and published!")
            print(f"[PASS] Ready for worksheet generation with {chunks_with_emb} chunks")
            print()
            print("Document is now available for:")
            print("  - Search and retrieval")
            print("  - Worksheet generation")
            print("  - Question answering")
        elif doc.status == 'failed':
            print("[FAIL] Document processing failed!")
            print(f"[FAIL] Error: {doc.error_message}")
            print(f"[FAIL] Remediation: {doc.remediation_hint or 'Check logs'}")
        elif chunks_with_emb == 0:
            print("[FAIL] Document has no chunks with embeddings!")
            print("[FAIL] Document cannot be used for worksheet generation")
            print("[FAIL] Status should be FAILED, not PUBLISHED")
        else:
            print(f"[WARN] Document status: {doc.status}")
            print(f"[WARN] Processing may still be in progress")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
