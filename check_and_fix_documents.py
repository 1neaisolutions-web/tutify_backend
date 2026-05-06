"""Check document status and reprocess if needed."""
import requests
import sys
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk, DocumentProcessingRun
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.jobs import run_ingestion_job_sync
from uuid import UUID

BASE = "http://127.0.0.1:8000"
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"
PACK_ID = "67ff7e11-a2e7-4eac-9177-9f682fb3ba0e"

print("=" * 70)
print("CHECKING AND FIXING DOCUMENTS")
print("=" * 70)
print()

# Login
print("1. Logging in...")
login_response = requests.post(
    f"{BASE}/api/v1/auth/login",
    json={"email": EMAIL, "password": PASSWORD},
    timeout=10
)
token = login_response.json()["access_token"]
print("   ✅ Login successful")
print()

# Get documents
print("2. Checking documents in pack...")
db: Session = SessionLocal()
try:
    pack_uuid = UUID(PACK_ID)
    documents = db.query(Document).filter(Document.pack_id == pack_uuid).all()
    
    print(f"   Found {len(documents)} documents total")
    print()
    
    for doc in documents:
        chunks_count = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        
        print(f"   Document: {doc.filename}")
        print(f"     Status: {doc.status}")
        print(f"     Total chunks: {chunks_count}")
        print(f"     Chunks with embeddings: {chunks_with_emb}")
        
        # Check if document needs reprocessing
        if doc.status == 'published' and chunks_with_emb == 0:
            print(f"     ⚠️  Published but no embeddings - needs reprocessing")
            
            # Check if there's a failed processing run
            latest_run = db.query(DocumentProcessingRun).filter(
                DocumentProcessingRun.document_id == doc.id
            ).order_by(DocumentProcessingRun.id.desc()).first()
            
            if latest_run:
                print(f"     Latest run status: {latest_run.status}")
                if latest_run.status == 'failed':
                    print(f"     Error: {latest_run.error_message}")
            
            # Reprocess document
            print(f"     🔄 Triggering reprocessing...")
            try:
                # Reset status to uploaded to allow reprocessing
                doc.status = DocumentStatus.UPLOADED.value
                doc.error_code = None
                doc.error_message = None
                doc.remediation_hint = None
                db.commit()
                
                # Trigger ingestion job
                run_ingestion_job_sync(doc.id)
                print(f"     ✅ Reprocessing triggered")
                
                # Check status after a moment
                db.refresh(doc)
                print(f"     New status: {doc.status}")
                
            except Exception as e:
                print(f"     ❌ Reprocessing failed: {e}")
                import traceback
                traceback.print_exc()
        elif doc.status != 'published':
            print(f"     Status: {doc.status} (not published)")
        else:
            print(f"     ✅ Document is properly processed")
        
        print()
        
finally:
    db.close()

print("=" * 70)
print("CHECK COMPLETE")
print("=" * 70)
