"""
Continuous Monitor - NEVER STOPS until document is fully processed.
Monitors, diagnoses, fixes, and processes until success.
"""
import sys
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ['OCR_ENGINE'] = 'easyocr'

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.services.ingestion_service import IngestionService
from uuid import UUID
import asyncio

# Auto-detect latest Mathematics document
def get_latest_document_id():
    """Get latest Mathematics document ID."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(
            Document.filename.like("%Mathematics%")
        ).order_by(Document.created_at.desc()).first()
        if doc:
            return str(doc.id)
        return "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"  # Fallback
    finally:
        db.close()

DOCUMENT_ID = get_latest_document_id()

def print_status(msg, status="INFO"):
    """Print status."""
    status_map = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]", "INFO": "[INFO]"}
    print(f"{status_map.get(status, '[INFO]')} {msg}")

def check_status():
    """Check current status."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
        if not doc:
            return None
        
        chunks_total = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        page_texts = db.query(PageText).filter(PageText.document_id == doc.id).count()
        total_chars = sum(p.char_count for p in db.query(PageText).filter(PageText.document_id == doc.id).all())
        
        return {
            "status": doc.status,
            "pages": doc.total_pages or 0,
            "page_texts": page_texts,
            "total_chars": total_chars,
            "chunks": chunks_total,
            "chunks_with_emb": chunks_with_emb,
            "error": doc.error_message,
            "doc": doc
        }
    finally:
        db.close()

def fix_issues():
    """Fix any issues."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
        if not doc:
            return False
        
        fixed = False
        
        # Delete empty page texts
        page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
        empty_texts = [pt for pt in page_texts if pt.char_count == 0]
        if empty_texts:
            print_status(f"Deleting {len(empty_texts)} empty page texts...", "INFO")
            for pt in empty_texts:
                db.delete(pt)
            db.commit()
            fixed = True
        
        # Reset status if needed
        if doc.status in ['failed', 'published']:
            chunks_with_emb = db.query(Chunk).filter(
                Chunk.document_id == doc.id,
                Chunk.embedding.isnot(None)
            ).count()
            
            if doc.status == 'published' and chunks_with_emb == 0:
                print_status("Resetting published status (no chunks)...", "INFO")
                doc.status = DocumentStatus.UPLOADED.value
                doc.error_code = None
                doc.error_message = None
                doc.remediation_hint = None
                if not doc.processing_metadata:
                    doc.processing_metadata = {}
                doc.processing_metadata['force_ocr'] = True
                db.commit()
                fixed = True
            elif doc.status == 'failed':
                print_status("Resetting failed status...", "INFO")
                doc.status = DocumentStatus.UPLOADED.value
                doc.error_code = None
                doc.error_message = None
                doc.remediation_hint = None
                if not doc.processing_metadata:
                    doc.processing_metadata = {}
                doc.processing_metadata['force_ocr'] = True
                db.commit()
                fixed = True
        
        return fixed
    finally:
        db.close()

async def process_document():
    """Process document."""
    db = SessionLocal()
    try:
        service = IngestionService(db)
        print_status(f"Processing document: {DOCUMENT_ID}", "INFO")
        await service.ingest_document(UUID(DOCUMENT_ID))
        print_status("Processing completed", "PASS")
    except Exception as e:
        print_status(f"Processing error: {e}", "WARN")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()

async def main():
    """Main - NEVER STOPS until document is ready."""
    print("="*70)
    print("CONTINUOUS MONITOR - NEVER STOPS")
    print("="*70)
    print_status("This script will monitor, diagnose, fix, and process until document is ready", "INFO")
    print_status("DOES NOT STOP until document is published with chunks and embeddings", "INFO")
    print()
    
    attempt = 0
    
    while True:
        attempt += 1
        print("\n" + "="*70)
        print(f"MONITORING CYCLE {attempt} - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
        # Check status
        status = check_status()
        if not status:
            print_status("Document not found!", "FAIL")
            time.sleep(10)
            continue
        
        print_status(f"Document ID: {DOCUMENT_ID}", "INFO")
        print_status(f"Status: {status['status']}", "INFO")
        print_status(f"Pages: {status['pages']}", "INFO")
        print_status(f"Page Texts: {status['page_texts']} (Total chars: {status['total_chars']})", "INFO")
        print_status(f"Chunks: {status['chunks']} total, {status['chunks_with_emb']} with embeddings", "INFO")
        
        # Show detailed progress
        if status['status'] == 'ocr_running':
            print_status(f"→ OCR RUNNING: Processing {status['page_texts']}/{status['pages']} pages", "INFO")
        elif status['status'] == 'chunking':
            print_status(f"→ CHUNKING: Created {status['chunks']} chunks", "INFO")
        elif status['status'] == 'embedding':
            print_status(f"→ EMBEDDING: {status['chunks_with_emb']}/{status['chunks']} chunks embedded", "INFO")
        elif status['status'] == 'indexing':
            print_status(f"→ INDEXING: Storing vectors in database", "INFO")
        
        if status['error']:
            print_status(f"Error: {status['error']}", "WARN")
        
        # Check if ready
        if status['status'] == 'published' and status['chunks_with_emb'] > 0:
            print_status("DOCUMENT IS READY!", "PASS")
            print_status(f"Chunks with embeddings: {status['chunks_with_emb']}", "PASS")
            print_status("Ready for worksheet generation!", "PASS")
            print("="*70)
            return
        
        # Fix issues
        print_status("Checking for issues...", "INFO")
        fixed = fix_issues()
        if fixed:
            print_status("Issues fixed, will process...", "PASS")
        
        # Process if needed
        if status['status'] == 'uploaded' or status['status'] == 'failed' or (status['status'] == 'published' and status['chunks_with_emb'] == 0):
            print_status("Starting processing...", "INFO")
            try:
                await process_document()
            except Exception as e:
                print_status(f"Processing error: {e}", "WARN")
                import traceback
                traceback.print_exc()
        
        # Wait before next check
        print_status("Waiting 10 seconds before next check...", "INFO")
        time.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[INFO] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_status(f"Fatal error: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        # DON'T EXIT - KEEP TRYING
        print_status("Error occurred but will continue monitoring...", "WARN")
        time.sleep(10)
        asyncio.run(main())  # Restart
