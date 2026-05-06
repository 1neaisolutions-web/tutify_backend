"""
Watch Until Ready - Continuously monitors and reports until document is fully ready.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk
from uuid import UUID

def get_latest_doc():
    """Get latest Mathematics document."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(
            Document.filename.like("%Mathematics%")
        ).order_by(Document.created_at.desc()).first()
        return doc
    finally:
        db.close()

def get_status(doc_id):
    """Get status."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
        if not doc:
            return None
        
        chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        pages = db.query(PageText).filter(PageText.document_id == doc.id).count()
        total_chars = sum(p.char_count for p in db.query(PageText).filter(PageText.document_id == doc.id).all())
        
        return {
            "status": doc.status,
            "pages": doc.total_pages or 0,
            "page_texts": pages,
            "total_chars": total_chars,
            "chunks": chunks,
            "chunks_emb": chunks_emb,
            "error": doc.error_message
        }
    finally:
        db.close()

def main():
    """Watch continuously."""
    print("="*70)
    print("WATCHING UNTIL DOCUMENT IS READY")
    print("="*70)
    print("Monitoring continuously...")
    print("Will report every 10 seconds until document is published with chunks")
    print("="*70)
    print()
    
    cycle = 0
    
    while True:
        cycle += 1
        doc = get_latest_doc()
        
        if not doc:
            print(f"[{time.strftime('%H:%M:%S')}] [ERROR] No document found!")
            time.sleep(10)
            continue
        
        status = get_status(str(doc.id))
        
        if not status:
            print(f"[{time.strftime('%H:%M:%S')}] [ERROR] Could not get status!")
            time.sleep(10)
            continue
        
        # Print status
        print(f"\n[{time.strftime('%H:%M:%S')}] CYCLE {cycle}")
        print(f"  Document: {doc.filename[:50]}...")
        print(f"  Status: {status['status'].upper()}")
        print(f"  Pages: {status['pages']} | Page Texts: {status['page_texts']} | Chars: {status['total_chars']:,}")
        print(f"  Chunks: {status['chunks']} | Chunks with Embeddings: {status['chunks_emb']}")
        
        if status['error']:
            print(f"  Error: {status['error'][:100]}")
        
        # Check if ready
        if status['status'] == 'published' and status['chunks_emb'] > 0:
            print()
            print("="*70)
            print("[SUCCESS] DOCUMENT IS READY!")
            print("="*70)
            print(f"Status: {status['status']}")
            print(f"Chunks with embeddings: {status['chunks_emb']}")
            print(f"Total chunks: {status['chunks']}")
            print("Ready for worksheet generation!")
            print("="*70)
            break
        
        # Show progress
        if status['status'] == 'ocr_running':
            print(f"  [OCR] Processing pages... ({status['page_texts']}/{status['pages']})")
        elif status['status'] == 'chunking':
            print(f"  [CHUNKING] Created {status['chunks']} chunks")
        elif status['status'] == 'embedding':
            print(f"  [EMBEDDING] Embedded {status['chunks_emb']}/{status['chunks']} chunks")
        elif status['status'] == 'indexing':
            print(f"  [INDEXING] Storing vectors...")
        elif status['status'] == 'failed':
            print(f"  [FAILED] {status['error'][:100]}")
            print(f"  Monitor script will fix and retry...")
        
        print(f"  Next check in 10 seconds...")
        time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Stopped by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
