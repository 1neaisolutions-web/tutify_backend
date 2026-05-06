"""
Master script: Ensures document is uploaded, processed, and ready.
Automatically fixes issues, reprocesses if needed, and monitors until complete.
DOES NOT STOP until document is verified ready for worksheet generation.
"""
import sys
import os
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Set OCR engine
os.environ['OCR_ENGINE'] = 'easyocr'

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.services.ingestion_service import IngestionService
from uuid import UUID
import asyncio

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"
DOCUMENT_ID = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"

def print_header(text):
    """Print header."""
    print("\n" + "="*70)
    print(text)
    print("="*70 + "\n")

def print_status(msg, status="INFO"):
    """Print status."""
    status_map = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]", "INFO": "[INFO]"}
    print(f"{status_map.get(status, '[INFO]')} {msg}")

def login():
    """Login."""
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code == 200:
        return r.json().get("access_token")
    return None

def get_api_status(token, doc_id):
    """Get status via API."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/api/v1/admin/documents/{doc_id}", headers=headers, timeout=10)
    if r.status_code == 200:
        return r.json()
    return None

def check_and_fix_document(db):
    """Check document and fix if needed."""
    doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
    if not doc:
        print_status("Document not found!", "FAIL")
        return False
    
    print_status(f"Document: {doc.filename}", "INFO")
    print_status(f"Current status: {doc.status}", "INFO")
    print_status(f"Pages: {doc.total_pages or 0}", "INFO")
    
    # Check page texts
    page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
    total_chars = sum(p.char_count for p in page_texts) if page_texts else 0
    
    print_status(f"Page texts: {len(page_texts)}, Total chars: {total_chars}", "INFO")
    
    # Check chunks
    chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
    chunks_with_emb = db.query(Chunk).filter(
        Chunk.document_id == doc.id,
        Chunk.embedding.isnot(None)
    ).count()
    
    print_status(f"Chunks: {chunks} total, {chunks_with_emb} with embeddings", "INFO")
    
    # Fix if needed
    needs_fix = False
    
    if doc.status == 'published' and chunks_with_emb == 0:
        print_status("Published but no chunks - needs reprocessing", "WARN")
        needs_fix = True
    elif doc.status == 'failed':
        print_status("Document failed - will reprocess", "WARN")
        needs_fix = True
    elif total_chars == 0 and len(page_texts) > 0:
        print_status("Page texts are empty - OCR needed", "WARN")
        needs_fix = True
    
    if needs_fix:
        print_status("Fixing document...", "INFO")
        
        # Delete empty page texts
        if total_chars == 0 and page_texts:
            print_status(f"Deleting {len(page_texts)} empty page texts...", "INFO")
            for pt in page_texts:
                db.delete(pt)
            db.commit()
        
        # Reset status
        doc.status = DocumentStatus.UPLOADED.value
        doc.error_code = None
        doc.error_message = None
        doc.remediation_hint = None
        if not doc.processing_metadata:
            doc.processing_metadata = {}
        doc.processing_metadata['force_ocr'] = True
        db.commit()
        
        print_status("Document reset to UPLOADED with force_ocr=True", "PASS")
        return True
    
    if doc.status == 'published' and chunks_with_emb > 0:
        print_status("Document is ready!", "PASS")
        return False  # No fix needed
    
    return True  # Needs processing

def monitor_processing(db, token):
    """Monitor processing with progress updates."""
    print_header("MONITORING PROCESSING")
    print_status("Watching for status updates...", "INFO")
    print_status("This may take 15-30 minutes for OCR", "INFO")
    print()
    
    start_time = time.time()
    last_status = None
    last_progress = -1
    
    while True:
        elapsed = time.time() - start_time
        
        # Check via API
        doc_api = get_api_status(token, DOCUMENT_ID)
        if doc_api:
            status = doc_api.get('status', 'unknown')
            progress = doc_api.get('progress_percentage', 0)
            step = doc_api.get('current_step', '')
            pages = doc_api.get('total_pages', 0)
            chunks = doc_api.get('chunks_count', 0)
            vectors = doc_api.get('vectors_stored', 0)
            error = doc_api.get('error_message', '')
            
            # Show status changes
            if status != last_status:
                elapsed_str = f"{int(elapsed/60)}m {int(elapsed%60)}s"
                print(f"[{elapsed_str}] STATUS: {status.upper()}")
                if step:
                    print(f"         Step: {step}")
                last_status = status
            
            # Show progress
            if progress != last_progress and progress > 0:
                bar_width = 40
                filled = int(bar_width * progress / 100)
                bar = "=" * filled + "-" * (bar_width - filled)
                print(f"         Progress: [{bar}] {progress}%")
                last_progress = progress
            
            # Show details
            if status in ['ocr_running', 'embedding', 'indexing', 'chunking']:
                if pages > 0:
                    print(f"         Pages: {pages}")
                if chunks > 0:
                    print(f"         Chunks: {chunks}")
                if vectors > 0:
                    print(f"         Vectors: {vectors}")
            
            # Check completion
            if status == 'published':
                print()
                if chunks > 0 and vectors > 0:
                    print_status(f"Processing completed! Chunks: {chunks}, Vectors: {vectors}", "PASS")
                    return True
                else:
                    print_status("Published but no chunks/vectors!", "FAIL")
                    return False
            elif status == 'failed':
                print()
                print_status(f"Processing failed: {error}", "FAIL")
                return False
        
        # Also check database directly
        doc_db = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
        if doc_db:
            chunks_db = db.query(Chunk).filter(
                Chunk.document_id == UUID(DOCUMENT_ID),
                Chunk.embedding.isnot(None)
            ).count()
            
            if doc_db.status == 'published' and chunks_db > 0:
                print()
                print_status(f"Verified in database: {chunks_db} chunks with embeddings", "PASS")
                return True
        
        time.sleep(5)  # Check every 5 seconds

def main():
    """Main execution."""
    print_header("ENSURE DOCUMENT IS READY")
    print_status("This script will:", "INFO")
    print_status("  1. Check document status", "INFO")
    print_status("  2. Fix issues if needed", "INFO")
    print_status("  3. Process document (OCR, chunks, embeddings)", "INFO")
    print_status("  4. Monitor progress in real-time", "INFO")
    print_status("  5. Verify everything works", "INFO")
    print_status("  6. Stop only when document is ready", "INFO")
    print()
    
    # Login
    print_status("Logging in...", "INFO")
    token = login()
    if not token:
        print_status("Login failed", "FAIL")
        sys.exit(1)
    print_status("Logged in", "PASS")
    
    db = SessionLocal()
    try:
        # Check and fix
        print_header("STEP 1: CHECKING DOCUMENT")
        needs_processing = check_and_fix_document(db)
        
        if not needs_processing:
            # Verify it's ready
            doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
            chunks = db.query(Chunk).filter(
                Chunk.document_id == UUID(DOCUMENT_ID),
                Chunk.embedding.isnot(None)
            ).count()
            
            if doc.status == 'published' and chunks > 0:
                print_header("DOCUMENT IS READY")
                print_status(f"Status: {doc.status}", "PASS")
                print_status(f"Chunks with embeddings: {chunks}", "PASS")
                print_status("Ready for worksheet generation!", "PASS")
                return
        
        # Process
        print_header("STEP 2: PROCESSING DOCUMENT")
        print_status("Starting ingestion pipeline...", "INFO")
        print_status("Steps: OCR → Chunking → Embedding → Indexing → QA → Publish", "INFO")
        print()
        
        ingestion_service = IngestionService(db)
        
        # Start processing in background
        import threading
        processing_done = threading.Event()
        processing_error = [None]
        
        def run_processing():
            try:
                result = asyncio.run(ingestion_service.ingest_document(UUID(DOCUMENT_ID)))
                processing_done.set()
            except Exception as e:
                processing_error[0] = str(e)
                processing_done.set()
        
        thread = threading.Thread(target=run_processing, daemon=True)
        thread.start()
        
        # Monitor
        print_header("STEP 3: MONITORING PROCESSING")
        success = monitor_processing(db, token)
        
        # Wait for thread
        thread.join(timeout=1)
        
        if processing_error[0]:
            print_status(f"Processing error: {processing_error[0]}", "FAIL")
            success = False
        
        # Final verification
        print_header("STEP 4: FINAL VERIFICATION")
        db.refresh(db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first())
        
        doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
        chunks = db.query(Chunk).filter(
            Chunk.document_id == UUID(DOCUMENT_ID),
            Chunk.embedding.isnot(None)
        ).count()
        
        print_status(f"Final status: {doc.status}", "INFO")
        print_status(f"Chunks with embeddings: {chunks}", "INFO")
        print()
        
        if doc.status == 'published' and chunks > 0:
            print_header("SUCCESS - DOCUMENT READY")
            print_status("Document is fully processed and ready!", "PASS")
            print_status(f"Document ID: {DOCUMENT_ID}", "INFO")
            print_status(f"Chunks: {chunks}", "INFO")
            print_status("Ready for: Worksheet generation, Search, Q&A", "PASS")
        else:
            print_header("FAILED")
            print_status("Document is not ready", "FAIL")
            if doc.status == 'failed':
                print_status(f"Error: {doc.error_message}", "FAIL")
            sys.exit(1)
            
    except Exception as e:
        print_status(f"Error: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
