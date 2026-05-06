"""
Check status of a specific document.
"""
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, DocumentProcessingRun, PageText, Chunk
from sqlalchemy import text

def check_document(document_id: str):
    """Check document status and details."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        
        if not doc:
            print(f"[FAIL] Document {document_id} not found")
            return
        
        print("=" * 80)
        print(f"DOCUMENT STATUS CHECK: {document_id}")
        print("=" * 80)
        print()
        
        print(f"Filename: {doc.filename}")
        print(f"Status: {doc.status}")
        print(f"Error Code: {doc.error_code}")
        print(f"Error Message: {doc.error_message[:200] if doc.error_message else 'None'}")
        print(f"Remediation Hint: {doc.remediation_hint[:200] if doc.remediation_hint else 'None'}")
        print()
        
        # Check processing metadata
        if doc.processing_metadata:
            meta = doc.processing_metadata
            print("Processing Metadata:")
            print(f"  PDF Type: {meta.get('pdf_type', 'unknown')}")
            print(f"  OCR Attempted: {meta.get('ocr_attempted', False)}")
            print(f"  Force OCR: {meta.get('force_ocr', False)}")
            if 'ocr_preflight' in meta:
                preflight = meta['ocr_preflight']
                print(f"  OCR Preflight:")
                print(f"    Tesseract Found: {preflight.get('tesseract_found', False)}")
                print(f"    Poppler Found: {preflight.get('poppler_found', False)}")
                print(f"    Poppler Path: {preflight.get('poppler_path', 'N/A')}")
        print()
        
        # Check processing runs
        runs = db.query(DocumentProcessingRun).filter(
            DocumentProcessingRun.document_id == document_id
        ).order_by(DocumentProcessingRun.started_at.desc()).all()
        
        print(f"Processing Runs: {len(runs)}")
        for i, run in enumerate(runs[:3], 1):  # Show last 3 runs
            print(f"  Run {i}:")
            print(f"    Status: {run.status}")
            print(f"    Step: {run.current_step}")
            print(f"    Progress: {run.progress_percentage}%")
            print(f"    Started: {run.started_at}")
            print(f"    Completed: {run.completed_at}")
            if run.error_message:
                print(f"    Error: {run.error_message[:150]}")
        print()
        
        # Check page texts
        page_count = db.query(PageText).filter(PageText.document_id == document_id).count()
        non_empty_pages = db.execute(
            text("""
                SELECT COUNT(*) 
                FROM page_texts 
                WHERE document_id = :d AND char_count > 0
            """),
            {"d": document_id}
        ).scalar_one()
        
        print(f"Page Texts:")
        print(f"  Total pages: {page_count}")
        print(f"  Non-empty pages: {non_empty_pages}")
        print()
        
        # Check chunks
        chunk_count = db.query(Chunk).filter(Chunk.document_id == document_id).count()
        chunks_with_vectors = db.execute(
            text("""
                SELECT COUNT(*) 
                FROM chunks 
                WHERE document_id = :d 
                  AND embedding_v IS NOT NULL
            """),
            {"d": document_id}
        ).scalar_one()
        
        print(f"Chunks:")
        print(f"  Total chunks: {chunk_count}")
        print(f"  Chunks with embeddings: {chunks_with_vectors}")
        print()
        
        # Recommendations
        print("=" * 80)
        print("RECOMMENDATIONS:")
        print("=" * 80)
        
        if doc.status == "failed":
            if "Poppler" in (doc.error_message or ""):
                print("[ACTION] Poppler error detected - backend should now have Poppler configured")
                print("[ACTION] Use 'Retry Processing' button in frontend")
                print("[ACTION] Or use: POST /api/v1/admin/documents/{document_id}/retry")
            else:
                print(f"[ACTION] Document failed with: {doc.error_code}")
                print(f"[ACTION] Check error message for details")
        elif doc.status == "published":
            print("[SUCCESS] Document is published and ready!")
        elif doc.status in ["text_extracting", "ocr_running", "chunking", "embedding", "indexing", "qa_validation"]:
            print(f"[INFO] Document is currently processing (status: {doc.status})")
            print("[ACTION] Wait for processing to complete or check status stream")
        else:
            print(f"[INFO] Document status: {doc.status}")
        
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        document_id = sys.argv[1]
    else:
        # Default to the first document that had Poppler error
        document_id = "9b684917-350d-4d18-bb6a-2007e1ab6c7a"
    
    check_document(document_id)
