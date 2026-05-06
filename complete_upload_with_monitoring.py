"""
Complete upload and processing with real-time monitoring.
Ensures document is uploaded, processed with OCR, chunks created, embeddings generated, and verified.
"""
import requests
import time
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

# File to upload
TARGET_FILE = "(ustad360.com) Mathematics 6 SNC 2023-24.pdf"

def find_pdf_file() -> Optional[Path]:
    """Find PDF file."""
    possible_paths = [
        Path(TARGET_FILE),
        Path(f"../{TARGET_FILE}"),
        Path(f"../../{TARGET_FILE}"),
    ]
    for search_dir in [Path("."), Path(".."), Path("../..")]:
        if search_dir.exists():
            try:
                for pdf_file in search_dir.rglob("*.pdf"):
                    if "Mathematics" in pdf_file.name and "6" in pdf_file.name:
                        possible_paths.append(pdf_file)
            except:
                pass
    for path in possible_paths:
        if path.exists():
            return path
    return None

def print_header(text: str):
    """Print section header."""
    print("\n" + "="*70)
    print(text)
    print("="*70 + "\n")

def print_status(msg: str, status: str = "INFO"):
    """Print status message."""
    status_map = {
        "PASS": "[PASS]",
        "FAIL": "[FAIL]",
        "WARN": "[WARN]",
        "INFO": "[INFO]"
    }
    print(f"{status_map.get(status, '[INFO]')} {msg}")

def login() -> Optional[str]:
    """Login."""
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=30
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception as e:
        print_status(f"Login failed: {e}", "FAIL")
    return None

def get_pack(token: str) -> Optional[str]:
    """Get or create pack."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE}/api/v1/admin/content-packs", headers=headers, timeout=10)
        if r.status_code == 200:
            packs = r.json()
            if packs:
                return packs[0]["id"]
    except:
        pass
    
    # Create pack
    pack_data = {
        "name": "Mathematics Books",
        "description": "Mathematics textbooks",
        "subject": "Mathematics",
        "grade": "6",
        "curriculum": "SNC"
    }
    try:
        r = requests.post(f"{BASE}/api/v1/admin/content-packs", json=pack_data, headers=headers, timeout=10)
        if r.status_code == 201:
            return r.json()["id"]
    except Exception as e:
        print_status(f"Failed to create pack: {e}", "FAIL")
    return None

def upload_document(token: str, pack_id: str, file_path: Path) -> Optional[str]:
    """Upload document."""
    url = f"{BASE}/api/v1/admin/documents"
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/pdf')}
            data = {
                'pack_id': pack_id,
                'title': 'Mathematics 6 SNC 2023-24',
                'force_ocr': 'true',
            }
            response = requests.post(url, files=files, data=data, headers=headers, timeout=300)
            
            if response.status_code == 201:
                doc_data = response.json()
                return doc_data.get('id')
    except Exception as e:
        print_status(f"Upload failed: {e}", "FAIL")
    return None

def get_document_status(token: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """Get document status."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE}/api/v1/admin/documents/{doc_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def monitor_with_progress(token: str, doc_id: str, max_minutes: int = 120):
    """Monitor with progress updates."""
    start_time = time.time()
    last_status = None
    last_progress = -1
    
    print_header("MONITORING PROCESSING")
    print_status("Watching for status updates...", "INFO")
    print_status("This may take 15-30 minutes for OCR processing", "INFO")
    print()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > max_minutes * 60:
            print_status(f"Timeout after {max_minutes} minutes", "FAIL")
            return False
        
        doc = get_document_status(token, doc_id)
        if not doc:
            time.sleep(5)
            continue
        
        status = doc.get('status', 'unknown')
        progress = doc.get('progress_percentage', 0)
        step = doc.get('current_step', '')
        pages = doc.get('total_pages', 0)
        chunks = doc.get('chunks_count', 0)
        vectors = doc.get('vectors_stored', 0)
        error = doc.get('error_message')
        
        # Show status changes
        if status != last_status:
            elapsed_str = f"{int(elapsed/60)}m {int(elapsed%60)}s"
            print(f"\n[{elapsed_str}] STATUS: {status.upper()}")
            if step:
                print(f"         Step: {step}")
            last_status = status
        
        # Show progress
        if progress != last_progress and progress > 0:
            bar_width = 40
            filled = int(bar_width * progress / 100)
            bar = "=" * filled + "-" * (bar_width - filled)
            print(f"         Progress: [{bar}] {progress}%")
            last_progress = progress
        
        # Show details for active processing
        if status in ['ocr_running', 'embedding', 'indexing', 'chunking']:
            if pages > 0:
                print(f"         Pages: {pages}")
            if chunks > 0:
                print(f"         Chunks: {chunks}")
            if vectors > 0:
                print(f"         Vectors: {vectors}")
        
        # Check completion
        if status == 'published':
            print()
            print_status(f"Processing completed!", "PASS")
            print_status(f"Pages: {pages}, Chunks: {chunks}, Vectors: {vectors}", "INFO")
            
            if chunks > 0 and vectors > 0:
                return True
            else:
                print_status("Published but no chunks/vectors found!", "FAIL")
                return False
        elif status == 'failed':
            print()
            print_status(f"Processing failed: {error}", "FAIL")
            return False
        
        time.sleep(5)  # Check every 5 seconds

def verify_final_status(token: str, doc_id: str) -> bool:
    """Verify final status."""
    print_header("FINAL VERIFICATION")
    
    doc = get_document_status(token, doc_id)
    if not doc:
        print_status("Could not get document status", "FAIL")
        return False
    
    status = doc.get('status', 'unknown')
    pages = doc.get('total_pages', 0)
    chunks = doc.get('chunks_count', 0)
    vectors = doc.get('vectors_stored', 0)
    
    print_status(f"Status: {status}", "INFO")
    print_status(f"Pages: {pages}", "INFO")
    print_status(f"Chunks: {chunks}", "INFO")
    print_status(f"Vectors: {vectors}", "INFO")
    print()
    
    if status == 'published' and chunks > 0 and vectors > 0:
        print_status("Document is ready for worksheet generation!", "PASS")
        return True
    else:
        print_status("Document not ready - missing chunks or vectors", "FAIL")
        return False

def main():
    """Main execution."""
    print_header("COMPLETE DOCUMENT UPLOAD AND PROCESSING")
    
    # Step 1: Find file
    print_header("STEP 1: FINDING PDF FILE")
    pdf_file = find_pdf_file()
    if not pdf_file:
        print_status("PDF file not found!", "FAIL")
        print_status(f"Looking for: {TARGET_FILE}", "INFO")
        sys.exit(1)
    print_status(f"Found: {pdf_file.absolute()}", "PASS")
    print_status(f"Size: {pdf_file.stat().st_size / 1024 / 1024:.2f} MB", "INFO")
    
    # Step 2: Health check
    print_header("STEP 2: CHECKING BACKEND")
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        if r.status_code != 200:
            print_status("Backend not responding", "FAIL")
            sys.exit(1)
    except Exception as e:
        print_status(f"Backend not running: {e}", "FAIL")
        sys.exit(1)
    print_status("Backend is running", "PASS")
    
    # Step 3: Login
    print_header("STEP 3: AUTHENTICATION")
    token = login()
    if not token:
        print_status("Login failed", "FAIL")
        sys.exit(1)
    print_status("Logged in successfully", "PASS")
    
    # Step 4: Get pack
    print_header("STEP 4: CONTENT PACK")
    pack_id = get_pack(token)
    if not pack_id:
        print_status("Failed to get/create pack", "FAIL")
        sys.exit(1)
    print_status(f"Using pack: {pack_id}", "PASS")
    
    # Step 5: Upload
    print_header("STEP 5: UPLOADING DOCUMENT")
    print_status("Uploading with force_ocr=True...", "INFO")
    doc_id = upload_document(token, pack_id, pdf_file)
    if not doc_id:
        print_status("Upload failed", "FAIL")
        sys.exit(1)
    print_status(f"Uploaded successfully: {doc_id}", "PASS")
    
    # Step 6: Monitor processing
    success = monitor_with_progress(token, doc_id, max_minutes=120)
    
    if not success:
        print_header("PROCESSING FAILED")
        print_status("Document processing did not complete successfully", "FAIL")
        print_status("Check error messages above", "INFO")
        sys.exit(1)
    
    # Step 7: Verify
    verified = verify_final_status(token, doc_id)
    
    if verified:
        print_header("SUCCESS - TASK COMPLETE")
        print_status("Document uploaded and processed successfully!", "PASS")
        print_status(f"Document ID: {doc_id}", "INFO")
        print_status("Ready for worksheet generation", "PASS")
        print()
    else:
        print_header("VERIFICATION FAILED")
        print_status("Document processing completed but verification failed", "FAIL")
        sys.exit(1)

if __name__ == "__main__":
    main()
