"""Check if pack has published documents with embeddings."""
import requests
import sys
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk
from uuid import UUID

BASE = "http://127.0.0.1:8000"
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"
PACK_ID = "67ff7e11-a2e7-4eac-9177-9f682fb3ba0e"

print("=" * 70)
print("CHECKING PACK CONTENT")
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

# Get documents in pack
print("2. Getting documents in pack...")
docs_response = requests.get(
    f"{BASE}/api/v1/admin/documents?pack_id={PACK_ID}",
    headers={"Authorization": f"Bearer {token}"},
    timeout=10
)
documents = docs_response.json()
print(f"   Found {len(documents)} documents")
for doc in documents:
    if isinstance(doc, dict):
        print(f"   - {doc.get('filename', 'N/A')}: {doc.get('status', 'N/A')}")
    else:
        print(f"   - {doc}")
print()

# Check database for chunks with embeddings
print("3. Checking database for chunks with embeddings...")
db: Session = SessionLocal()
try:
    pack_uuid = UUID(PACK_ID)
    
    # Get published documents
    published_docs = db.query(Document).filter(
        Document.pack_id == pack_uuid,
        Document.status == 'published'
    ).all()
    
    print(f"   Published documents: {len(published_docs)}")
    
    total_chunks = 0
    chunks_with_embeddings = 0
    
    for doc in published_docs:
        chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
        total_chunks += len(chunks)
        
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).all()
        chunks_with_embeddings += len(chunks_with_emb)
        
        print(f"   Document: {doc.filename}")
        print(f"     Total chunks: {len(chunks)}")
        print(f"     Chunks with embeddings: {len(chunks_with_emb)}")
    
    print()
    print(f"   Total chunks: {total_chunks}")
    print(f"   Chunks with embeddings: {chunks_with_embeddings}")
    
    if chunks_with_embeddings == 0:
        print()
        print("   ⚠️  WARNING: No chunks with embeddings found!")
        print("   This means worksheet generation will fail.")
        print("   Documents need to be processed and embedded first.")
    else:
        print()
        print("   ✅ Pack has content with embeddings!")
        print("   Worksheet generation should work.")
        
finally:
    db.close()

print()
print("=" * 70)
