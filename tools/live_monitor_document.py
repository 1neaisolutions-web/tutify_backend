"""
Live monitoring of document processing - shows real-time metrics without stopping.
Updates every 2 seconds showing pages processed, progress, chunks, etc.
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

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, DocumentProcessingRun, PageText, Chunk
from sqlalchemy import text

DOCUMENT_ID = "34ee0763-88fa-47d4-b696-ad15e4f9bb9b"

def get_live_metrics(document_id: str):
    """Get current live metrics from database."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return None
        
        # Page texts metrics
        total_pages = doc.total_pages or 0
        page_count = db.query(PageText).filter(PageText.document_id == document_id).count()
        non_empty_pages = db.execute(
            text("SELECT COUNT(*) FROM page_texts WHERE document_id = :d AND char_count > 0"),
            {"d": document_id}
        ).scalar_one()
        
        # Calculate pages processed percentage
        pages_processed_pct = (non_empty_pages / total_pages * 100) if total_pages > 0 else 0
        
        # Chunks metrics
        chunk_count = db.query(Chunk).filter(Chunk.document_id == document_id).count()
        chunks_with_vectors = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE document_id = :d AND embedding_v IS NOT NULL"),
            {"d": document_id}
        ).scalar_one()
        
        # Processing run metrics
        latest_run = db.query(DocumentProcessingRun).filter(
            DocumentProcessingRun.document_id == document_id
        ).order_by(DocumentProcessingRun.started_at.desc()).first()
        
        # Calculate total characters extracted
        total_chars = db.execute(
            text("SELECT SUM(char_count) FROM page_texts WHERE document_id = :d"),
            {"d": document_id}
        ).scalar_one() or 0
        
        return {
            "status": doc.status,
            "error_code": doc.error_code,
            "error_message": doc.error_message,
            "filename": doc.filename,
            "total_pages": total_pages,
            "pages_extracted": page_count,
            "pages_with_text": non_empty_pages,
            "pages_processed_pct": pages_processed_pct,
            "total_chars": total_chars,
            "chunks": chunk_count,
            "chunks_with_vectors": chunks_with_vectors,
            "current_step": latest_run.current_step if latest_run else None,
            "progress_pct": latest_run.progress_percentage if latest_run else 0,
            "pages_processed": latest_run.pages_processed if latest_run else 0,
            "chunks_created": latest_run.chunks_created if latest_run else 0,
            "vectors_stored": latest_run.vectors_stored if latest_run else 0,
            "started_at": latest_run.started_at if latest_run else None,
            "processing_metadata": doc.processing_metadata or {},
        }
    finally:
        db.close()

def format_time_elapsed(start_time):
    """Format elapsed time."""
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return f"{minutes}m {seconds}s"

def print_metrics_header():
    """Print metrics header."""
    print("\033[2J\033[H", end="")  # Clear screen (works on most terminals)
    print("=" * 80)
    print("LIVE DOCUMENT PROCESSING MONITOR")
    print("=" * 80)
    print(f"Document ID: {DOCUMENT_ID}")
    print(f"Monitoring: Real-time metrics (updates every 2 seconds)")
    print("=" * 80)
    print()

def print_metrics(metrics, elapsed_time):
    """Print formatted metrics."""
    if not metrics:
        print("[ERROR] Document not found")
        return
    
    # Status section
    status_color = ""
    if metrics["status"] == "published":
        status_color = "[SUCCESS]"
    elif metrics["status"] == "failed":
        status_color = "[FAIL]"
    elif metrics["status"] in ["ocr_running", "chunking", "embedding", "indexing", "qa_validation"]:
        status_color = "[PROCESSING]"
    else:
        status_color = "[INFO]"
    
    print(f"Status: {status_color} {metrics['status'].upper()}")
    print(f"Elapsed Time: {elapsed_time}")
    print(f"Filename: {metrics['filename']}")
    print()
    
    # Progress section
    print("-" * 80)
    print("PROGRESS METRICS:")
    print("-" * 80)
    print(f"Overall Progress: {metrics['progress_pct']}%")
    print(f"Current Step: {metrics['current_step'] or 'N/A'}")
    print()
    
    # Pages section
    print("-" * 80)
    print("PAGES METRICS:")
    print("-" * 80)
    print(f"Total Pages: {metrics['total_pages']}")
    print(f"Pages Extracted: {metrics['pages_extracted']}")
    print(f"Pages with Text: {metrics['pages_with_text']}")
    if metrics['total_pages'] > 0:
        pages_pct = (metrics['pages_with_text'] / metrics['total_pages']) * 100
        print(f"Pages Processed: {pages_pct:.1f}% ({metrics['pages_with_text']}/{metrics['total_pages']})")
        # Progress bar for pages
        bar_length = 40
        filled = int(bar_length * pages_pct / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"Progress: [{bar}] {pages_pct:.1f}%")
    print(f"Total Characters Extracted: {metrics['total_chars']:,}")
    print()
    
    # Processing run metrics
    if metrics['pages_processed'] and metrics['pages_processed'] > 0:
        print(f"Processing Run - Pages Processed: {metrics['pages_processed']}")
    if metrics['chunks_created'] and metrics['chunks_created'] > 0:
        print(f"Processing Run - Chunks Created: {metrics['chunks_created']}")
    if metrics['vectors_stored'] and metrics['vectors_stored'] > 0:
        print(f"Processing Run - Vectors Stored: {metrics['vectors_stored']}")
    print()
    
    # Chunks section
    print("-" * 80)
    print("CHUNKS & EMBEDDINGS:")
    print("-" * 80)
    print(f"Total Chunks: {metrics['chunks']}")
    print(f"Chunks with Embeddings: {metrics['chunks_with_vectors']}")
    if metrics['chunks'] > 0:
        chunks_pct = (metrics['chunks_with_vectors'] / metrics['chunks']) * 100
        print(f"Embedding Completion: {chunks_pct:.1f}%")
    print()
    
    # OCR info
    meta = metrics.get('processing_metadata', {})
    if 'ocr_preflight' in meta:
        preflight = meta['ocr_preflight']
        print("-" * 80)
        print("OCR CONFIGURATION:")
        print("-" * 80)
        print(f"Tesseract: {'[FOUND]' if preflight.get('tesseract_found') else '[NOT FOUND]'}")
        print(f"Poppler: {'[FOUND]' if preflight.get('poppler_found') else '[NOT FOUND]'}")
        if preflight.get('poppler_path'):
            print(f"Poppler Path: {preflight['poppler_path']}")
        print()
    
    # Errors section
    if metrics['error_code']:
        print("-" * 80)
        print("ERRORS:")
        print("-" * 80)
        print(f"Error Code: {metrics['error_code']}")
        if metrics['error_message']:
            print(f"Error Message: {metrics['error_message'][:200]}")
        print()
    
    # Estimated time remaining (rough estimate)
    if metrics['progress_pct'] > 0 and metrics['progress_pct'] < 100:
        elapsed_seconds = time.time() - (metrics['started_at'].timestamp() if metrics['started_at'] else time.time())
        if elapsed_seconds > 0:
            rate = metrics['progress_pct'] / elapsed_seconds  # % per second
            if rate > 0:
                remaining_pct = 100 - metrics['progress_pct']
                estimated_seconds = remaining_pct / rate
                estimated_minutes = int(estimated_seconds // 60)
                estimated_secs = int(estimated_seconds % 60)
                print("-" * 80)
                print(f"Estimated Time Remaining: ~{estimated_minutes}m {estimated_secs}s")
                print("-" * 80)
    
    print()
    print("Press Ctrl+C to stop monitoring (processing will continue)")
    print("=" * 80)

def monitor_live(document_id: str):
    """Monitor document processing with live updates."""
    start_time = time.time()
    last_metrics = None
    
    try:
        while True:
            metrics = get_live_metrics(document_id)
            
            if not metrics:
                print("[ERROR] Document not found")
                break
            
            elapsed_time = format_time_elapsed(start_time)
            print_metrics_header()
            print_metrics(metrics, elapsed_time)
            
            # Check if processing is complete
            if metrics['status'] in ['published', 'failed']:
                print()
                if metrics['status'] == 'published':
                    print("[SUCCESS] Processing completed successfully!")
                    print_final_summary(metrics)
                else:
                    print("[FAIL] Processing failed!")
                    if metrics['error_message']:
                        print(f"Error: {metrics['error_message']}")
                break
            
            # Wait before next update
            time.sleep(2)  # Update every 2 seconds
            
            # Track changes
            if last_metrics:
                if (metrics['pages_with_text'] != last_metrics['pages_with_text'] or
                    metrics['chunks'] != last_metrics['chunks'] or
                    metrics['status'] != last_metrics['status']):
                    # Something changed - metrics will be shown in next iteration
                    pass
            last_metrics = metrics
            
    except KeyboardInterrupt:
        print()
        print()
        print("=" * 80)
        print("Monitoring stopped by user")
        print("=" * 80)
        print()
        final_metrics = get_live_metrics(document_id)
        if final_metrics:
            print("Final Status:")
            print(f"  Status: {final_metrics['status']}")
            print(f"  Pages with Text: {final_metrics['pages_with_text']}/{final_metrics['total_pages']}")
            print(f"  Chunks: {final_metrics['chunks']}")
            print()
            print("Processing will continue in background.")
            print("Run this script again to check status.")

def print_final_summary(metrics):
    """Print final summary when processing completes."""
    print()
    print("=" * 80)
    print("FINAL SUMMARY:")
    print("=" * 80)
    print(f"Status: {metrics['status']}")
    print(f"Total Pages: {metrics['total_pages']}")
    print(f"Pages with Text: {metrics['pages_with_text']}")
    print(f"Total Characters: {metrics['total_chars']:,}")
    print(f"Chunks Created: {metrics['chunks']}")
    print(f"Chunks with Embeddings: {metrics['chunks_with_vectors']}")
    print(f"Embedding Completion: {(metrics['chunks_with_vectors']/metrics['chunks']*100) if metrics['chunks'] > 0 else 0:.1f}%")
    print("=" * 80)

if __name__ == "__main__":
    print("Starting live monitoring...")
    print("Document ID:", DOCUMENT_ID)
    print()
    time.sleep(1)  # Brief pause before starting
    
    monitor_live(DOCUMENT_ID)
