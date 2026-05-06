"""
Verify document upload status comprehensively.
"""
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk, PageText
from uuid import UUID

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

def login():
    """Login."""
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code == 200:
        return r.json().get("access_token")
    return None

def check_via_api(token):
    """Check via API."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # List all documents
    r = requests.get(f"{BASE}/api/v1/admin/documents", headers=headers, timeout=10)
    if r.status_code == 200:
        docs = r.json()
        print(f"\n[API] Found {len(docs)} documents:")
        for doc in docs[:5]:  # Show first 5
            print(f"  - {doc.get('filename', 'N/A')} | Status: {doc.get('status', 'N/A')} | Pages: {doc.get('total_pages', 0)} | Chunks: {doc.get('chunks_count', 0)}")
        return docs
    return []

def check_via_db():
    """Check via database."""
    db = SessionLocal()
    try:
        # Find Mathematics document
        docs = db.query(Document).filter(
            Document.filename.like("%Mathematics%")
        ).all()
        
        print(f"\n[DB] Found {len(docs)} Mathematics documents:")
        for doc in docs:
            chunks_total = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
            chunks_with_emb = db.query(Chunk).filter(
                Chunk.document_id == doc.id,
                Chunk.embedding.isnot(None)
            ).count()
            page_texts = db.query(PageText).filter(PageText.document_id == doc.id).count()
            
            print(f"\n  Document ID: {doc.id}")
            print(f"  Filename: {doc.filename}")
            print(f"  Status: {doc.status}")
            print(f"  Pages: {doc.total_pages or 0}")
            print(f"  Page Texts: {page_texts}")
            print(f"  Chunks: {chunks_total} total, {chunks_with_emb} with embeddings")
            print(f"  File Path: {doc.file_path}")
            print(f"  File Size: {doc.file_size / 1024 / 1024:.2f} MB" if doc.file_size else "  File Size: N/A")
            print(f"  Created: {doc.created_at}")
            print(f"  Error: {doc.error_message or 'None'}")
            
            # Check if file exists
            if doc.file_path:
                file_path = Path(doc.file_path)
                if file_path.exists():
                    print(f"  [PASS] File exists on disk")
                else:
                    print(f"  [FAIL] File NOT found on disk: {file_path}")
        
        return docs
    finally:
        db.close()

def main():
    """Main."""
    print("="*70)
    print("DOCUMENT UPLOAD VERIFICATION")
    print("="*70)
    
    # Check via database
    print("\n[1] Checking via Database...")
    docs = check_via_db()
    
    # Check via API
    print("\n[2] Checking via API...")
    token = login()
    if token:
        api_docs = check_via_api(token)
    else:
        print("[WARN] Could not login to check API")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    if docs:
        doc = docs[0]
        print(f"\nDocument: {doc.filename}")
        print(f"Status: {doc.status}")
        print(f"Pages: {doc.total_pages or 0}")
        
        if doc.status == 'uploaded':
            print("\n[PASS] Document uploaded successfully!")
            print("[INFO] Document is waiting for processing")
            print("[INFO] Background script should be processing it now")
        elif doc.status == 'published':
            db = SessionLocal()
            try:
                chunks_with_emb = db.query(Chunk).filter(
                    Chunk.document_id == doc.id,
                    Chunk.embedding.isnot(None)
                ).count()
                if chunks_with_emb > 0:
                    print("\n[PASS] Document fully processed and ready!")
                else:
                    print("\n[WARN] Document published but no chunks - needs reprocessing")
            finally:
                db.close()
        elif doc.status == 'failed':
            print(f"\n[FAIL] Processing failed: {doc.error_message}")
        else:
            print(f"\n[INFO] Document status: {doc.status} - processing in progress")
    else:
        print("\n[FAIL] No Mathematics document found!")
        print("[INFO] Document may not have been uploaded yet")
    
    print("="*70)

if __name__ == "__main__":
    main()
