"""
Continuous Progress Monitor - Reports every 5 seconds until document is ready.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk, DocumentProcessingRun
from uuid import UUID

def get_progress(doc_id):
    """Get detailed progress."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
        if not doc:
            return None
        
        # Get latest processing run
        try:
            run = db.query(DocumentProcessingRun).filter(
                DocumentProcessingRun.document_id == doc.id
            ).order_by(DocumentProcessingRun.started_at.desc()).first()
        except:
            run = None
        
        chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        pages = db.query(PageText).filter(PageText.document_id == doc.id).count()
        pages_with_text = db.query(PageText).filter(
            PageText.document_id == doc.id,
            PageText.char_count > 0
        ).count()
        total_chars = sum(p.char_count for p in db.query(PageText).filter(PageText.document_id == doc.id).all())
        
        return {
            "status": doc.status,
            "current_step": run.current_step if run else None,
            "progress": run.progress_percentage if run else 0,
            "pages": doc.total_pages or 0,
            "page_texts": pages,
            "pages_with_text": pages_with_text,
            "total_chars": total_chars,
            "chunks": chunks,
            "chunks_emb": chunks_emb,
            "error": doc.error_message,
            "filename": doc.filename
        }
    finally:
        db.close()

def main():
    """Monitor continuously."""
    print("="*80)
    print("CONTINUOUS PROGRESS MONITOR")
    print("="*80)
    print("Monitoring every 5 seconds...")
    print("Press Ctrl+C to stop")
    print("="*80)
    print()
    
    # Get document
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(
            Document.filename.like("%Mathematics%")
        ).order_by(Document.created_at.desc()).first()
        if not doc:
            print("[ERROR] No Mathematics document found!")
            return
        doc_id = str(doc.id)
    finally:
        db.close()
    
    cycle = 0
    last_status = None
    
    try:
        while True:
            cycle += 1
            progress = get_progress(doc_id)
            
            if not progress:
                print(f"[{time.strftime('%H:%M:%S')}] [ERROR] Could not get progress!")
                time.sleep(5)
                continue
            
            # Print header every cycle or when status changes
            if cycle == 1 or progress['status'] != last_status:
                print()
                print("="*80)
                print(f"[{time.strftime('%H:%M:%S')}] CYCLE {cycle}")
                print("="*80)
            
            last_status = progress['status']
            
            # Status line
            status_line = f"Status: {progress['status'].upper()}"
            if progress['current_step']:
                status_line += f" | Step: {progress['current_step']}"
            if progress['progress'] > 0:
                status_line += f" | Progress: {progress['progress']}%"
            print(status_line)
            
            # Document info
            print(f"Document: {progress['filename'][:60]}...")
            
            # Pages info
            pages_info = f"Pages: {progress['pages']} total"
            if progress['page_texts'] > 0:
                pages_info += f" | Page Texts: {progress['page_texts']}"
            if progress['pages_with_text'] > 0:
                pages_info += f" | With Text: {progress['pages_with_text']}"
            if progress['total_chars'] > 0:
                pages_info += f" | Characters: {progress['total_chars']:,}"
            print(pages_info)
            
            # Chunks info
            chunks_info = f"Chunks: {progress['chunks']} total"
            if progress['chunks_emb'] > 0:
                chunks_info += f" | With Embeddings: {progress['chunks_emb']}"
            print(chunks_info)
            
            # Error if any
            if progress['error']:
                print(f"[ERROR] {progress['error'][:100]}")
            
            # Progress indicators
            if progress['status'] == 'ocr_running':
                print(f"[OCR] Processing... {progress['pages_with_text']}/{progress['pages']} pages extracted")
            elif progress['status'] == 'chunking':
                print(f"[CHUNKING] Created {progress['chunks']} chunks")
            elif progress['status'] == 'embedding':
                print(f"[EMBEDDING] Embedded {progress['chunks_emb']}/{progress['chunks']} chunks")
            elif progress['status'] == 'indexing':
                print(f"[INDEXING] Storing vectors...")
            elif progress['status'] == 'qa_validation':
                print(f"[QA] Validating quality...")
            elif progress['status'] == 'failed':
                print(f"[FAILED] Monitor script will fix and retry...")
            
            # Check if ready
            if progress['status'] == 'published' and progress['chunks_emb'] > 0:
                print()
                print("="*80)
                print("[SUCCESS] DOCUMENT IS READY!")
                print("="*80)
                print(f"Status: {progress['status']}")
                print(f"Chunks with embeddings: {progress['chunks_emb']}")
                print(f"Total chunks: {progress['chunks']}")
                print("Ready for worksheet generation!")
                print("="*80)
                break
            
            # Wait
            print(f"Next check in 5 seconds...")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Stopped by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
