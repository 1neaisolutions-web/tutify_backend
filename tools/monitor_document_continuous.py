"""
Continuously monitor document processing from database.
Shows metrics and addresses issues.
"""
import os
import sys
import io
import time
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, DocumentProcessingRun, PageText, Chunk
from sqlalchemy import text

DOCUMENT_ID = "34ee0763-88fa-47d4-b696-ad15e4f9bb9b"

def get_full_metrics(document_id: str):
    """Get comprehensive metrics for document."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return None
        
        # Page texts
        page_count = db.query(PageText).filter(PageText.document_id == document_id).count()
        non_empty_pages = db.execute(
            text("SELECT COUNT(*) FROM page_texts WHERE document_id = :d AND char_count > 0"),
            {"d": document_id}
        ).scalar_one()
        
        total_chars = db.execute(
            text("SELECT SUM(char_count) FROM page_texts WHERE document_id = :d"),
            {"d": document_id}
        ).scalar_one() or 0
        
        # Chunks
        chunk_count = db.query(Chunk).filter(Chunk.document_id == document_id).count()
        chunks_with_vectors = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE document_id = :d AND embedding_v IS NOT NULL"),
            {"d": document_id}
        ).scalar_one()
        
        # Latest processing run
        latest_run = db.query(DocumentProcessingRun).filter(
            DocumentProcessingRun.document_id == document_id
        ).order_by(DocumentProcessingRun.started_at.desc()).first()
        
        return {
            "filename": doc.filename,
            "status": doc.status,
            "error_code": doc.error_code,
            "error_message": doc.error_message,
            "remediation_hint": doc.remediation_hint,
            "pages": page_count,
            "non_empty_pages": non_empty_pages,
            "total_chars": total_chars,
            "chunks": chunk_count,
            "chunks_with_vectors": chunks_with_vectors,
            "current_step": latest_run.current_step if latest_run else None,
            "progress": latest_run.progress_percentage if latest_run else None,
            "pages_processed": latest_run.pages_processed if latest_run else None,
            "chunks_created": latest_run.chunks_created if latest_run else None,
            "vectors_stored": latest_run.vectors_stored if latest_run else None,
            "started_at": latest_run.started_at if latest_run else None,
            "processing_metadata": doc.processing_metadata or {},
        }
    finally:
        db.close()

def print_metrics(metrics, elapsed_seconds):
    """Print formatted metrics."""
    print(f"\n[{elapsed_seconds}s] STATUS UPDATE")
    print("-" * 80)
    print(f"Filename: {metrics['filename']}")
    print(f"Status: {metrics['status']}")
    
    if metrics['current_step']:
        print(f"Current Step: {metrics['current_step']}")
    
    if metrics['progress'] is not None:
        print(f"Progress: {metrics['progress']}%")
    
    print()
    print("METRICS:")
    print(f"  Pages: {metrics['pages']} total, {metrics['non_empty_pages']} non-empty")
    if metrics['total_chars'] > 0:
        print(f"  Total Characters: {metrics['total_chars']:,}")
    
    print(f"  Chunks: {metrics['chunks']} total, {metrics['chunks_with_vectors']} with embeddings")
    
    if metrics['pages_processed']:
        print(f"  Pages Processed: {metrics['pages_processed']}")
    if metrics['chunks_created']:
        print(f"  Chunks Created: {metrics['chunks_created']}")
    if metrics['vectors_stored']:
        print(f"  Vectors Stored: {metrics['vectors_stored']}")
    
    # OCR info
    meta = metrics.get('processing_metadata', {})
    if 'ocr_preflight' in meta:
        preflight = meta['ocr_preflight']
        print()
        print("OCR CONFIGURATION:")
        print(f"  Tesseract Found: {preflight.get('tesseract_found', False)}")
        print(f"  Poppler Found: {preflight.get('poppler_found', False)}")
        if preflight.get('poppler_path'):
            print(f"  Poppler Path: {preflight['poppler_path']}")
    
    if meta.get('ocr_attempted'):
        print(f"  OCR Attempted: Yes")
    
    # Errors
    if metrics['error_code']:
        print()
        print("ERRORS:")
        print(f"  Error Code: {metrics['error_code']}")
        if metrics['error_message']:
            print(f"  Error Message: {metrics['error_message'][:300]}")
        if metrics['remediation_hint']:
            print(f"  Hint: {metrics['remediation_hint'][:200]}")
    
    print("-" * 80)

def analyze_issues(metrics):
    """Analyze and report issues."""
    if metrics['status'] == 'failed':
        print()
        print("=" * 80)
        print("ISSUE DETECTED - ANALYSIS:")
        print("=" * 80)
        
        error_code = metrics['error_code']
        error_message = metrics['error_message'] or ""
        
        if error_code == "OCR_ERROR" or "Poppler" in error_message:
            print("[ISSUE] Poppler/OCR Error")
            print()
            print("Diagnosis:")
            print(f"  - Poppler Found: {metrics['processing_metadata'].get('ocr_preflight', {}).get('poppler_found', False)}")
            print(f"  - Pages Extracted: {metrics['non_empty_pages']} / {metrics['pages']}")
            print(f"  - Chunks Created: {metrics['chunks']}")
            print()
            
            if "0xC0000135" in error_message or "DLL" in error_message:
                print("[ROOT CAUSE] Poppler DLL dependency missing")
                print()
                print("Solution:")
                print("  1. Install Microsoft VC++ Redistributable 2015-2022 (x64)")
                print("     Download: https://aka.ms/vs/17/release/vc_redist.x64.exe")
                print("  2. Run installer (may require admin)")
                print("  3. Restart backend server")
                print("  4. Retry document processing")
            else:
                print("[ROOT CAUSE] Poppler path or configuration issue")
                print()
                print("Solution:")
                print("  1. Verify Poppler path is correct")
                print("  2. Check backend logs for detailed error")
                print("  3. Retry processing after fixing")
        
        elif error_code == "TEXT_EXTRACTION_ERROR":
            print("[ISSUE] Text Extraction Failed")
            print("Solution: Enable OCR or check document format")
        
        elif error_code == "EMBEDDING_ERROR":
            print("[ISSUE] Embedding Generation Failed")
            print("Solution: Check embedding provider configuration")
        
        print()
        print("Next Steps:")
        print("  1. Fix the issue above")
        print("  2. Use 'Retry Processing' button in frontend")
        print(f"  3. Or call: POST /api/v1/admin/documents/{DOCUMENT_ID}/retry")

def monitor_continuous(document_id: str, check_interval=3, max_minutes=60):
    """Continuously monitor document processing."""
    print("=" * 80)
    print(f"CONTINUOUS MONITORING: {document_id}")
    print("=" * 80)
    print(f"Check interval: {check_interval} seconds")
    print(f"Max duration: {max_minutes} minutes")
    print()
    
    start_time = time.time()
    last_status = None
    last_metrics = None
    
    try:
        while True:
            elapsed = int(time.time() - start_time)
            
            if elapsed > max_minutes * 60:
                print(f"\n[WARN] Monitoring timeout after {max_minutes} minutes")
                break
            
            metrics = get_full_metrics(document_id)
            
            if not metrics:
                print(f"[FAIL] Document {document_id} not found")
                break
            
            # Print update if status or metrics changed
            if metrics['status'] != last_status or metrics != last_metrics:
                print_metrics(metrics, elapsed)
                last_status = metrics['status']
                last_metrics = metrics.copy()
            
            # Check for completion
            if metrics['status'] == 'published':
                print()
                print("=" * 80)
                print("[SUCCESS] DOCUMENT PROCESSING COMPLETED!")
                print("=" * 80)
                print()
                print("FINAL METRICS:")
                print(f"  Status: {metrics['status']}")
                print(f"  Pages: {metrics['pages']} total, {metrics['non_empty_pages']} non-empty")
                print(f"  Total Characters: {metrics['total_chars']:,}")
                print(f"  Chunks: {metrics['chunks']} total")
                print(f"  Chunks with Embeddings: {metrics['chunks_with_vectors']}")
                print()
                print("[PASS] Document is ready for use!")
                break
            
            # Check for failure
            if metrics['status'] == 'failed':
                analyze_issues(metrics)
                break
            
            # Wait before next check
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        print("\n[INFO] Monitoring stopped by user")
    except Exception as e:
        print(f"\n[ERROR] Monitoring error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    monitor_continuous(DOCUMENT_ID, check_interval=3, max_minutes=60)
