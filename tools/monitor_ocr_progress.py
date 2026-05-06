"""
Monitor OCR progress for a document without blocking or changing anything.
Shows real-time progress updates.
"""
import sys
import io
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, DocumentProcessingRun
from uuid import UUID

# Document ID can be passed as command-line argument or set here
DOCUMENT_ID = None

def get_status():
    """Get current document status."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
        if not doc:
            return None
        
        # Get page texts
        page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
        pages_with_text = sum(1 for p in page_texts if p.char_count > 0)
        total_chars = sum(p.char_count for p in page_texts)
        
        # Get latest processing run
        run = db.query(DocumentProcessingRun).filter(
            DocumentProcessingRun.document_id == doc.id
        ).order_by(DocumentProcessingRun.started_at.desc()).first()
        
        return {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "status": doc.status,
            "total_pages": doc.total_pages or 0,
            "pages_with_text": pages_with_text,
            "total_chars": total_chars,
            "error_code": doc.error_code,
            "error_message": doc.error_message,
            "run_status": run.status if run else None,
            "run_step": run.current_step if run else None,
            "run_progress": run.progress_percentage if run else None,
            "run_pages_processed": run.pages_processed if run else None,
            "run_started": run.started_at if run else None,
        }
    finally:
        db.close()

def format_time_ago(dt):
    """Format datetime as time ago."""
    if not dt:
        return "N/A"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
    minutes = int(elapsed / 60)
    seconds = int(elapsed % 60)
    return f"{minutes}m {seconds}s"

def print_status(status, iteration=0):
    """Print formatted status."""
    print("\n" + "=" * 80)
    print(f"OCR MONITORING - Check #{iteration + 1}")
    print("=" * 80)
    print(f"Document: {status['filename']}")
    print(f"Status: {status['status']}")
    print(f"Total Pages: {status['total_pages']}")
    print(f"Pages with Text: {status['pages_with_text']} / {status['total_pages']}")
    print(f"Total Characters: {status['total_chars']:,}")
    
    if status['run_status']:
        print(f"\nProcessing Run:")
        print(f"  Status: {status['run_status']}")
        print(f"  Step: {status['run_step'] or 'N/A'}")
        print(f"  Progress: {status['run_progress'] or 0}%")
        print(f"  Pages Processed: {status['run_pages_processed'] or 0}")
        if status['run_started']:
            print(f"  Started: {format_time_ago(status['run_started'])} ago")
    
    if status['error_code']:
        print(f"\n[ERROR] {status['error_code']}")
    if status['error_message']:
        print(f"[ERROR] {status['error_message'][:200]}")
    
    # Progress assessment
    print("\n" + "-" * 80)
    if status['status'] == 'ocr_running':
        if status['pages_with_text'] == 0:
            print("[STUCK?] No pages have text yet - OCR may be converting images or processing")
        elif status['pages_with_text'] < status['total_pages']:
            progress_pct = (status['pages_with_text'] / status['total_pages']) * 100
            print(f"[PROGRESS] {progress_pct:.1f}% pages completed ({status['pages_with_text']}/{status['total_pages']})")
        else:
            print("[COMPLETE] All pages have text!")
    elif status['status'] == 'failed':
        print("[FAILED] Processing failed - check error messages above")
    elif status['status'] == 'published':
        print("[SUCCESS] Document is published!")
    
    print("=" * 80)

def main():
    """Monitor OCR progress."""
    global DOCUMENT_ID
    
    # Get document ID from command line or use default
    if len(sys.argv) > 1:
        DOCUMENT_ID = sys.argv[1]
    elif DOCUMENT_ID is None:
        # Try to find most recent document in OCR status
        db = SessionLocal()
        try:
            recent = db.query(Document).filter(
                Document.status.in_(['ocr_running', 'text_extracting', 'normalizing'])
            ).order_by(Document.created_at.desc()).first()
            if recent:
                DOCUMENT_ID = str(recent.id)
                print(f"[INFO] Auto-selected most recent OCR document: {recent.filename}")
            else:
                print("[ERROR] No document ID provided and no OCR documents found")
                print("Usage: python tools/monitor_ocr_progress.py <document_uuid>")
                return 1
        finally:
            db.close()
    
    print("=" * 80)
    print("OCR PROGRESS MONITOR")
    print("=" * 80)
    print(f"Monitoring document: {DOCUMENT_ID}")
    print("This script polls every 5 seconds - press Ctrl+C to stop")
    print("=" * 80)
    
    last_pages_with_text = -1
    last_total_chars = -1
    iteration = 0
    no_progress_count = 0
    
    try:
        while True:
            status = get_status()
            if not status:
                print(f"\n[ERROR] Document {DOCUMENT_ID} not found in database")
                break
            
            print_status(status, iteration)
            
            # Check for progress
            if status['pages_with_text'] > last_pages_with_text or status['total_chars'] > last_total_chars:
                print("\n[PROGRESS DETECTED] Pages or characters increased!")
                no_progress_count = 0
            else:
                no_progress_count += 1
                if no_progress_count >= 6:  # 30 seconds with no progress
                    print(f"\n[WARNING] No progress detected for {no_progress_count * 5} seconds")
                    if status['status'] == 'ocr_running' and status['pages_with_text'] == 0:
                        print("[ISSUE] OCR has been running but no pages have text yet.")
                        print("  Possible causes:")
                        print("  1. PDF-to-image conversion is taking a long time (193 pages)")
                        print("  2. OCR is processing but very slowly")
                        print("  3. OCR may be stuck/hanging")
                        print("  Recommendation: Check backend terminal logs for OCR activity")
            
            last_pages_with_text = status['pages_with_text']
            last_total_chars = status['total_chars']
            
            # Check if done
            if status['status'] in ['published', 'failed']:
                print(f"\n[FINAL STATUS] Document reached final status: {status['status']}")
                break
            
            iteration += 1
            print(f"\nWaiting 5 seconds... (Ctrl+C to stop)")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n[STOPPED] Monitoring stopped by user")
    except Exception as e:
        print(f"\n[ERROR] Monitoring error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
