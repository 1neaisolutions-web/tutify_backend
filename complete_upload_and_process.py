"""
Complete Automated Upload and Processing System
Uploads document, monitors processing, diagnoses failures, fixes issues, and retries until successful.
DOES NOT STOP until document is fully processed and verified.
"""
import requests
import time
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
import traceback

sys.path.insert(0, str(Path(__file__).parent))

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

# Set OCR engine
os.environ['OCR_ENGINE'] = 'easyocr'

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.services.ingestion_service import IngestionService
from uuid import UUID
import asyncio

TARGET_FILENAME = "(ustad360.com) Mathematics 6 SNC 2023-24.pdf"
MAX_RETRIES = 5
MAX_WAIT_MINUTES = 120  # 2 hours for OCR processing

def print_header(text: str):
    """Print header."""
    print("\n" + "="*70)
    print(text)
    print("="*70 + "\n")

def print_status(msg: str, status: str = "INFO"):
    """Print status."""
    status_map = {
        "PASS": "[PASS]",
        "FAIL": "[FAIL]",
        "WARN": "[WARN]",
        "INFO": "[INFO]"
    }
    print(f"{status_map.get(status, '[INFO]')} {msg}")

def find_pdf_file() -> Optional[Path]:
    """Find PDF file in multiple locations."""
    print_status("Searching for PDF file...", "INFO")
    
    possible_paths = [
        Path(TARGET_FILENAME),
        Path(f"../{TARGET_FILENAME}"),
        Path(f"../../{TARGET_FILENAME}"),
        Path(f"uploads/documents/{TARGET_FILENAME}"),
        Path(__file__).parent / TARGET_FILENAME,
        Path(__file__).parent.parent / TARGET_FILENAME,
        Path.home() / "Desktop" / TARGET_FILENAME,
        Path.home() / "Downloads" / TARGET_FILENAME,
        Path.home() / "OneDrive" / "Desktop" / TARGET_FILENAME,
    ]
    
    # Search recursively in common directories
    search_dirs = [
        Path("."),
        Path(".."),
        Path("../.."),
        Path(__file__).parent,
        Path(__file__).parent.parent,
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "OneDrive" / "Desktop",
    ]
    
    for search_dir in search_dirs:
        if search_dir.exists():
            try:
                for pdf_file in search_dir.rglob("*.pdf"):
                    if "Mathematics" in pdf_file.name and "6" in pdf_file.name and "SNC" in pdf_file.name:
                        possible_paths.append(pdf_file)
            except Exception:
                pass
    
    for path in possible_paths:
        if path.exists() and path.is_file():
            print_status(f"Found PDF: {path}", "PASS")
            return path
    
    print_status("PDF file not found!", "FAIL")
    print_status("Please ensure the file exists in one of these locations:", "INFO")
    for path in possible_paths[:5]:
        print_status(f"  - {path}", "INFO")
    return None

def test_backend_health(max_wait: int = 300) -> bool:
    """Test backend health, wait if needed. DOES NOT STOP until backend is ready."""
    print_status("Checking backend health...", "INFO")
    print_status(f"Will wait up to {max_wait} seconds for backend to start", "INFO")
    
    for attempt in range(max_wait):
        try:
            r = requests.get(f"{BASE}/health", timeout=5)
            if r.status_code == 200:
                print_status("Backend is running", "PASS")
                return True
        except Exception:
            pass
        
        if attempt < max_wait - 1:
            if attempt % 10 == 0:  # Print every 10 seconds
                print_status(f"Waiting for backend... ({attempt}s / {max_wait}s)", "INFO")
            time.sleep(1)
    
    print_status("Backend not accessible after waiting - will keep trying", "WARN")
    # Don't give up - keep trying
    print_status("Continuing to retry backend connection...", "INFO")
    return False

def login() -> Optional[str]:
    """Login and get token."""
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=30
        )
        if r.status_code == 200:
            token = r.json().get("access_token")
            print_status("Login successful", "PASS")
            return token
        else:
            print_status(f"Login failed: {r.status_code}", "FAIL")
            return None
    except Exception as e:
        print_status(f"Login exception: {e}", "FAIL")
        return None

def get_or_create_pack(token: str) -> Optional[str]:
    """Get or create content pack."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try to get existing pack
    try:
        r = requests.get(f"{BASE}/api/v1/admin/content-packs", headers=headers, timeout=10)
        if r.status_code == 200:
            packs = r.json()
            if packs:
                pack_id = packs[0]["id"]
                print_status(f"Using existing pack: {pack_id}", "PASS")
                return pack_id
    except Exception as e:
        print_status(f"Could not list packs: {e}", "WARN")
    
    # Create new pack
    pack_data = {
        "name": "Mathematics Books",
        "description": "Mathematics textbooks and resources",
        "subject": "Mathematics",
        "grade": "6",
        "curriculum": "SNC"
    }
    
    try:
        r = requests.post(
            f"{BASE}/api/v1/admin/content-packs",
            json=pack_data,
            headers=headers,
            timeout=10
        )
        if r.status_code == 201:
            pack = r.json()
            pack_id = pack["id"]
            print_status(f"Created new pack: {pack_id}", "PASS")
            return pack_id
        else:
            print_status(f"Failed to create pack: {r.status_code}", "FAIL")
            return None
    except Exception as e:
        print_status(f"Exception creating pack: {e}", "FAIL")
        return None

def upload_document(token: str, pack_id: str, file_path: Path) -> Optional[str]:
    """Upload document."""
    print_status(f"Uploading: {file_path.name}", "INFO")
    print_status(f"File size: {file_path.stat().st_size / 1024 / 1024:.2f} MB", "INFO")
    
    url = f"{BASE}/api/v1/admin/documents"
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/pdf')}
            data = {
                'pack_id': pack_id,
                'title': file_path.stem.replace('_', ' '),
                'force_ocr': 'true',  # Force OCR for scanned PDF
            }
            
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=300
            )
            
            if response.status_code == 201:
                doc_data = response.json()
                document_id = doc_data.get('id')
                if document_id:
                    print_status(f"Document uploaded: {document_id}", "PASS")
                    return document_id
                else:
                    print_status("No document ID in response", "FAIL")
                    return None
            else:
                print_status(f"Upload failed: {response.status_code}", "FAIL")
                print_status(f"Response: {response.text[:200]}", "FAIL")
                return None
    except Exception as e:
        print_status(f"Upload exception: {e}", "FAIL")
        traceback.print_exc()
        return None

def get_api_status(token: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """Get document status via API."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE}/api/v1/admin/documents/{doc_id}", headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        print_status(f"API status error: {e}", "WARN")
        return None

def diagnose_and_fix(db, doc_id: str) -> bool:
    """Diagnose issues and fix them."""
    print_header("DIAGNOSING ISSUES")
    
    doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
    if not doc:
        print_status("Document not found in database", "FAIL")
        return False
    
    print_status(f"Document: {doc.filename}", "INFO")
    print_status(f"Status: {doc.status}", "INFO")
    print_status(f"Pages: {doc.total_pages or 0}", "INFO")
    
    # Check page texts
    page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
    total_chars = sum(p.char_count for p in page_texts) if page_texts else 0
    
    print_status(f"Page texts: {len(page_texts)}, Total chars: {total_chars}", "INFO")
    
    # Check chunks
    chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
    chunks_with_emb = db.query(Chunk).filter(
        Chunk.document_id == doc.id,
        Chunk.embedding.isnot(None)
    ).count()
    
    print_status(f"Chunks: {chunks} total, {chunks_with_emb} with embeddings", "INFO")
    
    # Diagnose issues
    issues = []
    
    if doc.status == 'failed':
        issues.append("Status is FAILED")
        error_msg = doc.error_message or "Unknown error"
        print_status(f"Error: {error_msg}", "WARN")
    
    if total_chars == 0 and len(page_texts) > 0:
        issues.append("Page texts are empty (OCR needed)")
    
    if doc.status == 'published' and chunks_with_emb == 0:
        issues.append("Published but no chunks/embeddings")
    
    if not issues:
        print_status("No issues detected", "PASS")
        return True
    
    # Fix issues
    print_header("FIXING ISSUES")
    
    # Delete empty page texts
    if total_chars == 0 and page_texts:
        print_status(f"Deleting {len(page_texts)} empty page texts...", "INFO")
        for pt in page_texts:
            db.delete(pt)
        db.commit()
        print_status("Empty page texts deleted", "PASS")
    
    # Reset status
    if doc.status in ['failed', 'published']:
        print_status(f"Resetting status from {doc.status} to UPLOADED", "INFO")
        doc.status = DocumentStatus.UPLOADED.value
        doc.error_code = None
        doc.error_message = None
        doc.remediation_hint = None
        
        # Ensure force_ocr is set
        if not doc.processing_metadata:
            doc.processing_metadata = {}
        doc.processing_metadata['force_ocr'] = True
        db.commit()
        print_status("Status reset", "PASS")
    
    return True

async def process_document(doc_id: str):
    """Process document using ingestion service."""
    print_header("STARTING DOCUMENT PROCESSING")
    
    db = SessionLocal()
    try:
        service = IngestionService(db)
        print_status(f"Processing document: {doc_id}", "INFO")
        await service.ingest_document(UUID(doc_id))
        print_status("Processing completed", "PASS")
    except Exception as e:
        print_status(f"Processing error: {e}", "FAIL")
        traceback.print_exc()
        raise
    finally:
        db.close()

def monitor_until_ready(token: str, doc_id: str) -> bool:
    """Monitor document until it's ready. DOES NOT STOP until document is published with chunks."""
    print_header("MONITORING PROCESSING")
    print_status("Monitoring will continue until document is fully processed", "INFO")
    print_status("This may take 30-60 minutes for OCR processing of 193 pages", "INFO")
    
    start_time = time.time()
    last_status = None
    last_progress = -1
    stuck_count = 0
    consecutive_errors = 0
    
    while True:
        elapsed_minutes = (time.time() - start_time) / 60
        
        # Extended timeout for large documents
        if elapsed_minutes > MAX_WAIT_MINUTES:
            print_status(f"\nTimeout after {MAX_WAIT_MINUTES} minutes - will diagnose and retry", "WARN")
            return False
        
        # Get status
        doc = get_api_status(token, doc_id)
        
        if doc:
            consecutive_errors = 0
            status = doc.get('status', 'unknown')
            progress = doc.get('progress_percentage', 0)
            step = doc.get('current_step', '')
            pages = doc.get('total_pages', 0)
            chunks = doc.get('chunks_count', 0)
            vectors = doc.get('vectors_stored', 0)
            error = doc.get('error_message', '')
            
            # Check if stuck (but allow longer for OCR)
            if status == last_status and progress == last_progress:
                stuck_count += 1
            else:
                stuck_count = 0
            
            # More lenient stuck detection for OCR phase
            if status == 'ocr_running':
                stuck_threshold = 200  # ~10 minutes for OCR
            else:
                stuck_threshold = 60  # ~3 minutes for other phases
            
            if stuck_count > stuck_threshold:
                print_status(f"\nProcessing appears stuck at {status} - will diagnose and retry", "WARN")
                return False
            
            # Print status with more detail
            step_display = step if step else status
            print(f"\r[INFO] Status: {status:15} | Step: {step_display:20} | Progress: {progress:3}% | Pages: {pages:3} | Chunks: {chunks:5} | Vectors: {vectors:5} | Time: {elapsed_minutes:.1f}m", end="", flush=True)
            
            # Check completion
            if status == 'published':
                if chunks > 0 and vectors > 0:
                    print("\n")
                    print_status(f"Document ready! Chunks: {chunks}, Vectors: {vectors}", "PASS")
                    return True
                else:
                    print("\n")
                    print_status("Published but no chunks - will diagnose and reprocess", "WARN")
                    return False
            
            if status == 'failed':
                print("\n")
                print_status(f"Processing failed: {error}", "FAIL")
                print_status("Will diagnose issue and retry", "INFO")
                return False
            
            last_status = status
            last_progress = progress
        else:
            consecutive_errors += 1
            if consecutive_errors > 10:
                print_status(f"\nToo many consecutive errors getting status - will retry", "WARN")
                return False
            print(f"\r[WARN] Could not get status (attempt {consecutive_errors})...", end="", flush=True)
        
        time.sleep(3)  # Check every 3 seconds

def verify_final_status(token: str, doc_id: str) -> bool:
    """Verify final status."""
    print_header("FINAL VERIFICATION")
    
    doc = get_api_status(token, doc_id)
    if not doc:
        print_status("Could not get document status", "FAIL")
        return False
    
    status = doc.get('status', 'unknown')
    chunks = doc.get('chunks_count', 0)
    vectors = doc.get('vectors_stored', 0)
    
    print_status(f"Status: {status}", "INFO")
    print_status(f"Chunks: {chunks}", "INFO")
    print_status(f"Vectors: {vectors}", "INFO")
    
    if status == 'published' and chunks > 0 and vectors > 0:
        print_status("VERIFICATION PASSED - Document is ready!", "PASS")
        return True
    else:
        print_status("VERIFICATION FAILED - Document not ready", "FAIL")
        return False

async def main():
    """Main execution."""
    print_header("COMPLETE AUTOMATED UPLOAD AND PROCESSING SYSTEM")
    print_status("This script will upload, process, monitor, diagnose, and fix until successful", "INFO")
    print_status("DOES NOT STOP until document is fully processed and verified", "INFO")
    
    # Step 1: Find PDF
    pdf_file = find_pdf_file()
    if not pdf_file:
        print_status("Cannot proceed without PDF file", "FAIL")
        sys.exit(1)
    
    # Step 2: Health check - keep retrying until backend is ready
    print_status("Waiting for backend to be ready...", "INFO")
    backend_ready = False
    while not backend_ready:
        backend_ready = test_backend_health(max_wait=60)
        if not backend_ready:
            print_status("Backend not ready yet, waiting 10 seconds before retry...", "WARN")
            time.sleep(10)
            print_status("Retrying backend connection...", "INFO")
    
    # Step 3: Login
    token = login()
    if not token:
        print_status("Cannot proceed without authentication", "FAIL")
        sys.exit(1)
    
    # Step 4: Get or create pack
    pack_id = get_or_create_pack(token)
    if not pack_id:
        print_status("Cannot proceed without pack", "FAIL")
        sys.exit(1)
    
    # Step 5: Upload document
    doc_id = upload_document(token, pack_id, pdf_file)
    if not doc_id:
        print_status("Upload failed", "FAIL")
        sys.exit(1)
    
    # Step 6: Process with retries - DOES NOT STOP until successful
    attempt = 0
    while True:
        attempt += 1
        print_header(f"ATTEMPT {attempt} - PROCESSING UNTIL SUCCESS")
        print_status("This script will NOT STOP until document is fully processed", "INFO")
        
        # Diagnose and fix
        print_status("Diagnosing current state...", "INFO")
        db = SessionLocal()
        try:
            diagnose_and_fix(db, doc_id)
        except Exception as e:
            print_status(f"Diagnosis error: {e}", "WARN")
            traceback.print_exc()
        finally:
            db.close()
        
        # Process document
        print_status("Starting document processing...", "INFO")
        try:
            await process_document(doc_id)
            print_status("Processing call completed", "PASS")
        except Exception as e:
            print_status(f"Processing error: {e}", "WARN")
            traceback.print_exc()
            print_status("Will diagnose and retry...", "INFO")
            time.sleep(5)
        
        # Monitor until ready - CONTINUOUSLY, NEVER STOPS
        print_status("Monitoring processing progress...", "INFO")
        print_status("MONITORING WILL CONTINUE UNTIL DOCUMENT IS READY - DO NOT STOP", "INFO")
        
        monitoring_result = monitor_until_ready(token, doc_id)
        
        # Verify final status
        if verify_final_status(token, doc_id):
            print_header("SUCCESS - ALL DONE!")
            print_status("Document is fully processed and ready for worksheet generation", "PASS")
            print_status(f"Total attempts: {attempt}", "INFO")
            return
        
        # If we get here, processing didn't complete successfully - KEEP TRYING
        print_status(f"Attempt {attempt} did not complete successfully", "WARN")
        print_status("Will continue monitoring and retrying...", "INFO")
        print_status("DO NOT STOP - KEEPING MONITORING UNTIL SUCCESS", "INFO")
        time.sleep(10)
        
        # Refresh token if needed
        new_token = login()
        if new_token:
            token = new_token
            print_status("Token refreshed", "INFO")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[INFO] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_status(f"Fatal error: {e}", "FAIL")
        traceback.print_exc()
        sys.exit(1)
