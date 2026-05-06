"""
Monitor and Fix - Reports EVERY step, fixes issues, continues until document is ready.
"""
import sys
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Use tesseract (more reliable, already configured)
os.environ['OCR_ENGINE'] = 'tesseract'

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk, DocumentProcessingRun
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.services.ingestion_service import IngestionService
from uuid import UUID
import asyncio

def get_latest_document_id():
    """Get latest Mathematics document ID."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(
            Document.filename.like("%Mathematics%")
        ).order_by(Document.created_at.desc()).first()
        if doc:
            return str(doc.id), doc.filename
        return None, None
    finally:
        db.close()

def print_step(step, message, status="INFO"):
    """Print step with timestamp."""
    timestamp = time.strftime('%H:%M:%S')
    status_map = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]", "INFO": "[INFO]"}
    print(f"[{timestamp}] {status_map.get(status, '[INFO]')} {step}: {message}")

def check_status(doc_id):
    """Check detailed status."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
        if not doc:
            return None
        
        # Get latest processing run
        try:
            processing_run = db.query(DocumentProcessingRun).filter(
                DocumentProcessingRun.document_id == doc.id
            ).order_by(DocumentProcessingRun.started_at.desc()).first()
        except:
            processing_run = None
        
        chunks_total = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        page_texts = db.query(PageText).filter(PageText.document_id == doc.id).count()
        total_chars = sum(p.char_count for p in db.query(PageText).filter(PageText.document_id == doc.id).all())
        
        return {
            "status": doc.status,
            "current_step": processing_run.current_step if processing_run else None,
            "progress": processing_run.progress_percentage if processing_run else 0,
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

def fix_and_reset(doc_id):
    """Fix issues and reset."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
        if not doc:
            return False
        
        print_step("FIX", "Checking for issues...", "INFO")
        
        # Delete empty page texts
        page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
        empty_texts = [pt for pt in page_texts if pt.char_count == 0]
        if empty_texts:
            print_step("FIX", f"Deleting {len(empty_texts)} empty page texts", "WARN")
            for pt in empty_texts:
                db.delete(pt)
            db.commit()
        
        # Reset status
        if doc.status in ['failed', 'published']:
            chunks_with_emb = db.query(Chunk).filter(
                Chunk.document_id == doc.id,
                Chunk.embedding.isnot(None)
            ).count()
            
            if chunks_with_emb == 0:
                print_step("FIX", f"Resetting status from {doc.status} to UPLOADED", "WARN")
                doc.status = DocumentStatus.UPLOADED.value
                doc.error_code = None
                doc.error_message = None
                doc.remediation_hint = None
                if not doc.processing_metadata:
                    doc.processing_metadata = {}
                doc.processing_metadata['force_ocr'] = True
                db.commit()
                print_step("FIX", "Status reset successfully", "PASS")
                return True
        
        return False
    finally:
        db.close()

async def process_document(doc_id):
    """Process document."""
    print_step("PROCESS", "Starting document ingestion pipeline", "INFO")
    db = SessionLocal()
    try:
        service = IngestionService(db)
        await service.ingest_document(UUID(doc_id))
        print_step("PROCESS", "Ingestion pipeline completed", "PASS")
    except Exception as e:
        print_step("PROCESS", f"Error: {str(e)[:100]}", "FAIL")
        raise
    finally:
        db.close()

async def main():
    """Main - NEVER STOPS."""
    print("="*70)
    print("MONITOR AND FIX - REPORTS EVERY STEP")
    print("="*70)
    print()
    
    # Get latest document
    doc_id, filename = get_latest_document_id()
    if not doc_id:
        print_step("ERROR", "No Mathematics document found!", "FAIL")
        return
    
    print_step("INIT", f"Monitoring document: {filename}", "INFO")
    print_step("INIT", f"Document ID: {doc_id}", "INFO")
    print()
    
    cycle = 0
    
    while True:
        cycle += 1
        print("\n" + "-"*70)
        print(f"CYCLE {cycle} - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-"*70)
        
        # Check status
        status = check_status(doc_id)
        if not status:
            print_step("ERROR", "Document not found!", "FAIL")
            time.sleep(10)
            continue
        
        # Report current status
        print_step("STATUS", f"{status['status'].upper()}", "INFO")
        if status['current_step']:
            print_step("STEP", f"{status['current_step']}", "INFO")
        if status['progress'] > 0:
            print_step("PROGRESS", f"{status['progress']}%", "INFO")
        
        print_step("PAGES", f"{status['page_texts']}/{status['pages']} pages processed", "INFO")
        print_step("TEXT", f"{status['total_chars']:,} characters extracted", "INFO")
        print_step("CHUNKS", f"{status['chunks']} total, {status['chunks_with_emb']} with embeddings", "INFO")
        
        # Check if ready
        if status['status'] == 'published' and status['chunks_with_emb'] > 0:
            print()
            print("="*70)
            print_step("SUCCESS", "DOCUMENT IS READY!", "PASS")
            print_step("SUCCESS", f"Chunks with embeddings: {status['chunks_with_emb']}", "PASS")
            print_step("SUCCESS", "Ready for worksheet generation!", "PASS")
            print("="*70)
            return
        
        # Report what's happening
        if status['status'] == 'uploaded':
            print_step("OCR", "Document uploaded, waiting for OCR...", "INFO")
        elif status['status'] == 'text_extracting':
            print_step("OCR", "Extracting text from PDF...", "INFO")
        elif status['status'] == 'ocr_running':
            print_step("OCR", f"Running OCR on {status['pages']} pages (this takes 15-30 min)...", "INFO")
            print_step("OCR", f"Progress: {status['page_texts']}/{status['pages']} pages processed", "INFO")
        elif status['status'] == 'normalizing':
            print_step("NORMALIZE", "Normalizing extracted text...", "INFO")
        elif status['status'] == 'chunking':
            print_step("CHUNK", f"Creating chunks from text...", "INFO")
            print_step("CHUNK", f"Created {status['chunks']} chunks so far", "INFO")
        elif status['status'] == 'embedding':
            print_step("EMBED", f"Generating embeddings...", "INFO")
            print_step("EMBED", f"Embedded {status['chunks_with_emb']}/{status['chunks']} chunks", "INFO")
        elif status['status'] == 'indexing':
            print_step("INDEX", "Storing vectors in database...", "INFO")
        elif status['status'] == 'qa_validation':
            print_step("QA", "Running quality validation...", "INFO")
        elif status['status'] == 'failed':
            print_step("ERROR", f"Processing failed: {status['error']}", "FAIL")
        
        # Fix and process if needed
        needs_processing = False
        
        if status['status'] == 'uploaded':
            needs_processing = True
            print_step("PROCESS", "Document is uploaded, starting processing...", "INFO")
        elif status['status'] == 'failed':
            needs_processing = True
            print_step("PROCESS", "Document failed, fixing and reprocessing...", "WARN")
        elif status['status'] == 'qa_validation' and status['chunks'] == 0:
            needs_processing = True
            print_step("PROCESS", "QA validation but no chunks, reprocessing...", "WARN")
        elif status['status'] == 'published' and status['chunks_with_emb'] == 0:
            needs_processing = True
            print_step("PROCESS", "Published but no chunks, reprocessing...", "WARN")
        
        if needs_processing:
            # Fix first
            if fix_and_reset(doc_id) or status['status'] in ['uploaded', 'failed', 'qa_validation']:
                print_step("PROCESS", "Starting document processing...", "INFO")
                try:
                    await process_document(doc_id)
                    print_step("PROCESS", "Processing completed, checking status...", "PASS")
                except Exception as e:
                    print_step("PROCESS", f"Error: {str(e)[:100]}", "WARN")
                    import traceback
                    traceback.print_exc()
        
        # Wait before next check
        print_step("WAIT", "Checking again in 5 seconds...", "INFO")
        time.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[INFO] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_step("FATAL", f"Error: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        print_step("RETRY", "Will continue monitoring...", "WARN")
        time.sleep(10)
        asyncio.run(main())
