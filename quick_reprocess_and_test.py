"""Quick reprocess check and end-to-end test."""
import requests
import sys
import time
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk
from uuid import UUID

BASE = "http://127.0.0.1:8000"
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"
PACK_ID = "67ff7e11-a2e7-4eac-9177-9f682fb3ba0e"

def print_status(msg):
    print(f"[*] {msg}")

def print_success(msg):
    print(f"[+] {msg}")

def print_error(msg):
    print(f"[-] {msg}")

def print_warning(msg):
    print(f"[!] {msg}")

# Step 1: Login
print_status("Logging in...")
try:
    login_response = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10
    )
    if login_response.status_code != 200:
        print_error(f"Login failed: {login_response.status_code}")
        sys.exit(1)
    token = login_response.json()["access_token"]
    print_success("Login successful")
except Exception as e:
    print_error(f"Login error: {e}")
    sys.exit(1)

# Step 2: Check document status
print_status("Checking document status...")
db: Session = SessionLocal()
try:
    pack_uuid = UUID(PACK_ID)
    documents = db.query(Document).filter(Document.pack_id == pack_uuid).all()
    
    if not documents:
        print_error("No documents found")
        sys.exit(1)
    
    doc = documents[0]
    doc_id = str(doc.id)
    
    chunks_with_emb = db.query(Chunk).filter(
        Chunk.document_id == doc.id,
        Chunk.embedding.isnot(None)
    ).count()
    
    print_status(f"Document: {doc.filename}")
    print_status(f"Status: {doc.status}")
    print_status(f"Chunks with embeddings: {chunks_with_emb}")
    
    if chunks_with_emb > 0:
        print_success("Document has embeddings - ready for testing!")
        should_reprocess = False
    else:
        print_warning("Document has no embeddings")
        print_warning("Note: OCR processing 193 pages will take 15-30 minutes")
        print_warning("To reprocess: Set OCR_ENGINE=easyocr and run check_and_fix_documents.py")
        should_reprocess = False  # Skip auto-reprocessing to avoid hanging
        
finally:
    db.close()

# Step 3: Run end-to-end test
print("\n" + "="*70)
print_status("Running end-to-end test...")
print("="*70 + "\n")

import subprocess
result = subprocess.run(
    [sys.executable, "test_end_to_end.py"],
    cwd=".",
    capture_output=False
)

if result.returncode == 0:
    print_success("\nAll tests passed!")
else:
    if chunks_with_emb == 0:
        print_warning("\nSome tests failed because document needs OCR processing")
        print_warning("To complete the flow:")
        print_warning("1. Set OCR_ENGINE=easyocr in .env or environment")
        print_warning("2. Run: python check_and_fix_documents.py")
        print_warning("3. Wait for processing to complete (15-30 minutes)")
        print_warning("4. Run: python test_end_to_end.py again")
    else:
        print_error("\nSome tests failed - check output above")

sys.exit(result.returncode)
