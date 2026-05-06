"""Reprocess document via API and test end-to-end flow."""
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

# Step 2: Get document ID
print_status("Finding document to reprocess...")
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
    print_status(f"Current chunks with embeddings: {chunks_with_emb}")
    
    if chunks_with_emb > 0:
        print_success("Document already has embeddings - skipping reprocessing")
        should_reprocess = False
    else:
        print_warning("Document has no embeddings - will reprocess")
        should_reprocess = True
        
finally:
    db.close()

# Step 3: Reprocess if needed (via API - async)
if should_reprocess:
    print_status("Triggering document reprocessing via API...")
    print_warning("Note: This may take several minutes for OCR processing")
    print_warning("EasyOCR will download models on first use (~500MB)")
    
    try:
        # Reset document status first
        db: Session = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
            if doc:
                from app.domains.content_ingestion.enums import DocumentStatus
                doc.status = DocumentStatus.UPLOADED.value
                doc.error_code = None
                doc.error_message = None
                doc.remediation_hint = None
                db.commit()
                print_success("Document status reset to UPLOADED")
        finally:
            db.close()
        
        # Trigger reprocessing via background job
        print_status("Starting background processing job...")
        from app.domains.content_ingestion.jobs import run_ingestion_job_sync
        
        # Set OCR_ENGINE to easyocr
        import os
        os.environ['OCR_ENGINE'] = 'easyocr'
        
        print_status("Running ingestion pipeline (this may take 5-15 minutes)...")
        print_status("Processing 193 pages with EasyOCR...")
        
        # Run sync but with progress updates
        import threading
        import queue
        
        progress_queue = queue.Queue()
        error_queue = queue.Queue()
        
        def run_job():
            try:
                run_ingestion_job_sync(UUID(doc_id))
                progress_queue.put("completed")
            except Exception as e:
                error_queue.put(str(e))
        
        job_thread = threading.Thread(target=run_job, daemon=True)
        job_thread.start()
        
        # Monitor progress
        start_time = time.time()
        last_status_check = 0
        dots = 0
        
        while job_thread.is_alive():
            elapsed = time.time() - start_time
            if elapsed - last_status_check > 10:  # Check every 10 seconds
                db: Session = SessionLocal()
                try:
                    doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
                    if doc:
                        print_status(f"Status: {doc.status} (elapsed: {int(elapsed)}s)")
                finally:
                    db.close()
                last_status_check = elapsed
            
            # Show progress dots
            if int(elapsed) % 5 == 0:
                dots = (dots + 1) % 4
                print(f"\r[Processing{'...'[:dots]:<3}]", end='', flush=True)
            
            time.sleep(1)
            
            # Timeout after 30 minutes
            if elapsed > 1800:
                print_error("\nProcessing timeout after 30 minutes")
                sys.exit(1)
        
        # Check for errors
        if not error_queue.empty():
            error = error_queue.get()
            print_error(f"\nProcessing failed: {error}")
            sys.exit(1)
        
        elapsed = time.time() - start_time
        print_success(f"\nProcessing completed in {int(elapsed)} seconds")
        
        # Verify results
        db: Session = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
            chunks_with_emb_after = db.query(Chunk).filter(
                Chunk.document_id == UUID(doc_id),
                Chunk.embedding.isnot(None)
            ).count()
            
            print_status(f"Final status: {doc.status}")
            print_status(f"Chunks with embeddings: {chunks_with_emb_after}")
            
            if chunks_with_emb_after > 0:
                print_success("Document successfully processed with embeddings!")
            else:
                print_warning("Document processed but no embeddings found")
        finally:
            db.close()
            
    except KeyboardInterrupt:
        print_error("\nProcessing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Reprocessing error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# Step 4: Run end-to-end test
print("\n" + "="*70)
print_status("Running end-to-end test...")
print("="*70 + "\n")

import subprocess
result = subprocess.run(
    [sys.executable, "test_end_to_end.py"],
    cwd=".",
    capture_output=False
)

sys.exit(result.returncode)
