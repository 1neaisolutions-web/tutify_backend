"""
Upload a PDF book to vector database via API and verify processing.
This script handles authentication, pack creation, document upload, OCR processing, and verification.
"""
import requests
import time
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"  # Admin account
PASSWORD = "123456789aA!"

# File to upload - check multiple possible locations
def find_pdf_file() -> Optional[Path]:
    """Find the PDF file in common locations."""
    target_filename = "(ustad360.com) Mathematics 6 SNC 2023-24.pdf"
    
    possible_paths = [
        Path(target_filename),
        Path(f"../{target_filename}"),
        Path(f"../../{target_filename}"),
        Path(f"uploads/documents/{target_filename}"),
        Path(__file__).parent / target_filename,
        Path(__file__).parent.parent / target_filename,
    ]
    
    # Also search recursively in common directories
    search_dirs = [
        Path("."),
        Path(".."),
        Path("../.."),
        Path(__file__).parent,
        Path(__file__).parent.parent,
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
            return path
    
    return None

PDF_FILE = find_pdf_file()

# Colors for terminal output (ASCII-safe for Windows)
def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"{title}")
    print(f"{'='*70}\n")

def print_success(msg: str):
    """Print success message."""
    print(f"[PASS] {msg}")

def print_error(msg: str):
    """Print error message."""
    print(f"[FAIL] {msg}")

def print_warning(msg: str):
    """Print warning message."""
    print(f"[WARN] {msg}")

def print_info(msg: str):
    """Print info message."""
    print(f"  {msg}")

def test_health() -> bool:
    """Test health endpoint."""
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        return r.status_code == 200
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def login() -> Optional[str]:
    """Login and get token."""
    try:
        print_info(f"Attempting login with email: {EMAIL}")
        r = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=30
        )
        if r.status_code == 200:
            token = r.json().get("access_token")
            print_success("Login successful")
            return token
        else:
            print_error(f"Login failed: {r.status_code} - {r.text}")
    except Exception as e:
        print_error(f"Login exception: {e}")
    return None

def get_or_create_pack(token: str) -> Optional[str]:
    """Get existing pack or create a new one."""
    print_section("2. Getting or Creating Content Pack")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try to list existing packs
    try:
        r = requests.get(
            f"{BASE}/api/v1/admin/content-packs",
            headers=headers,
            timeout=10
        )
        if r.status_code == 200:
            packs = r.json()
            if packs:
                pack_id = packs[0]["id"]
                print_success(f"Using existing pack: {pack_id}")
                print_info(f"Pack name: {packs[0].get('name', 'N/A')}")
                return pack_id
    except Exception as e:
        print_warning(f"Could not list packs: {e}")
    
    # Create new pack
    print_info("Creating new content pack...")
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
            print_success(f"Created new pack: {pack_id}")
            return pack_id
        else:
            print_error(f"Failed to create pack: {r.status_code} - {r.text}")
    except Exception as e:
        print_error(f"Exception creating pack: {e}")
    
    return None

def upload_document(token: str, pack_id: str, file_path: Path) -> Optional[str]:
    """Upload document and return document_id."""
    print_section("3. Uploading Document")
    
    if not file_path.exists():
        print_error(f"File not found: {file_path}")
        return None
    
    # Try non-streaming endpoint first (more reliable)
    url = f"{BASE}/api/v1/admin/documents"
    
    print_info(f"Uploading: {file_path.name}")
    print_info(f"File size: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
    print_info(f"To pack: {pack_id}")
    print_info("Note: This will use OCR since force_ocr=True")
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/pdf')}
            data = {
                'pack_id': pack_id,
                'title': file_path.stem.replace('_', ' '),
                'force_ocr': 'true',  # Force OCR for scanned PDFs
            }
            headers = {'Authorization': f'Bearer {token}'}
            
            print_info("Sending upload request...")
            # Reset file pointer
            f.seek(0)
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=300  # 5 minutes for large files
            )
            
            if response.status_code == 201:
                # Non-streaming endpoint returns document directly
                doc_data = response.json()
                document_id = doc_data.get('id')
                if document_id:
                    print_success(f"Document uploaded successfully: {document_id}")
                    print_info(f"Status: {doc_data.get('status', 'unknown')}")
                    return document_id
                else:
                    print_error("Upload succeeded but no document ID in response")
                    print_error(f"Response: {response.text[:500]}")
                    return None
            else:
                print_error(f"Upload failed: {response.status_code}")
                print_error(f"Response: {response.text[:500]}")
                return None
                
    except Exception as e:
        print_error(f"Upload exception: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_document_status(token: str, document_id: str) -> Optional[Dict[str, Any]]:
    """Check document processing status."""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.get(
            f"{BASE}/api/v1/admin/documents/{document_id}",
            headers=headers,
            timeout=10
        )
        if r.status_code == 200:
            return r.json()
        else:
            print_error(f"Failed to get document status: {r.status_code}")
            return None
    except Exception as e:
        print_error(f"Exception checking status: {e}")
        return None

def monitor_processing(token: str, document_id: str, max_wait_minutes: int = 60) -> bool:
    """Monitor document processing until complete."""
    print_section("4. Monitoring Processing Status")
    
    print_info(f"Document ID: {document_id}")
    print_info(f"Max wait time: {max_wait_minutes} minutes")
    print_info("This may take 15-30 minutes for OCR processing...")
    
    start_time = time.time()
    last_status = None
    
    while True:
        elapsed = (time.time() - start_time) / 60
        if elapsed > max_wait_minutes:
            print_error(f"Timeout after {max_wait_minutes} minutes")
            return False
        
        doc = check_document_status(token, document_id)
        if not doc:
            time.sleep(10)
            continue
        
        status = doc.get('status', 'unknown')
        progress = doc.get('progress_percentage', 0)
        error = doc.get('error_message')
        
        if status != last_status:
            print_info(f"Status changed: {status} ({progress}%)")
            last_status = status
        
        if status == 'published':
            chunks_count = doc.get('chunks_count', 0)
            vectors_stored = doc.get('vectors_stored', 0)
            
            print_info(f"Total pages: {doc.get('total_pages', 'N/A')}")
            print_info(f"Chunks created: {chunks_count}")
            print_info(f"Vectors stored: {vectors_stored}")
            
            # Verify chunks are actually saved
            if chunks_count == 0 or vectors_stored == 0:
                print_error("Document marked as published but has no chunks/embeddings!")
                print_error("This indicates a processing error. Document will be marked as FAILED.")
                return False
            
            print_success("Document processing completed!")
            return True
        elif status == 'failed':
            print_error(f"Processing failed: {error}")
            print_info(f"Error code: {doc.get('error_code', 'N/A')}")
            print_info(f"Remediation: {doc.get('remediation_hint', 'N/A')}")
            return False
        
        # Show progress for long-running steps
        if status in ['ocr_running', 'embedding', 'indexing']:
            print_info(f"Processing... {status} ({progress}%) - Elapsed: {elapsed:.1f} min")
        
        time.sleep(10)  # Check every 10 seconds

def verify_vector_db(token: str, document_id: str) -> bool:
    """Verify document is saved in vector DB."""
    print_section("5. Verifying Vector Database")
    
    doc = check_document_status(token, document_id)
    if not doc:
        print_error("Could not get document details")
        return False
    
    chunks_count = doc.get('chunks_count', 0)
    vectors_stored = doc.get('vectors_stored', 0)
    status = doc.get('status', 'unknown')
    
    print_info(f"Document status: {status}")
    print_info(f"Chunks created: {chunks_count}")
    print_info(f"Vectors stored: {vectors_stored}")
    
    if status == 'published' and chunks_count > 0 and vectors_stored > 0:
        print_success("Document successfully saved in vector database!")
        print_success(f"Ready for search and retrieval with {chunks_count} chunks")
        return True
    elif status == 'published' and chunks_count == 0:
        print_warning("Document published but no chunks found")
        return False
    else:
        print_warning(f"Document not fully processed yet (status: {status})")
        return False

def main():
    """Main execution flow."""
    print_section("Upload Book to Vector Database")
    print_info("This script will:")
    print_info("  1. Authenticate with the API")
    print_info("  2. Get or create a content pack")
    print_info("  3. Upload the PDF document")
    print_info("  4. Monitor OCR and processing")
    print_info("  5. Verify it's saved in vector DB")
    print()
    
    # Check if PDF file exists
    global PDF_FILE
    if not PDF_FILE:
        PDF_FILE = find_pdf_file()
    
    if not PDF_FILE or not PDF_FILE.exists():
        print_error("PDF file not found!")
        print_info("Looking for: 3183b057-1bed-4f6b-9d42-14fe2f6b46c3_1769415085.pdf")
        print_info("Expected locations:")
        print_info("  - uploads/documents/")
        print_info("  - ../uploads/documents/")
        sys.exit(1)
    
    print_success(f"Found PDF file: {PDF_FILE.absolute()}")
    print_info(f"File size: {PDF_FILE.stat().st_size / 1024 / 1024:.2f} MB")
    print()
    
    # Step 1: Health check
    print_section("1. Health Check")
    if not test_health():
        print_error("Backend server is not running!")
        print_info("Start the backend with: python START_BACKEND_SIMPLE.ps1")
        sys.exit(1)
    print_success("Backend server is running")
    
    # Step 2: Login
    token = login()
    if not token:
        print_error("Authentication failed. Exiting.")
        sys.exit(1)
    
    # Step 3: Get or create pack
    pack_id = get_or_create_pack(token)
    if not pack_id:
        print_error("Could not get or create pack. Exiting.")
        sys.exit(1)
    
    # Step 4: Upload document
    document_id = upload_document(token, pack_id, PDF_FILE)
    if not document_id:
        print_error("Document upload failed. Exiting.")
        sys.exit(1)
    
    # Step 5: Monitor processing
    success = monitor_processing(token, document_id, max_wait_minutes=90)  # Increased timeout for OCR
    if not success:
        print_error("Processing did not complete successfully")
        print_error("Document may have failed or is missing chunks/embeddings")
        sys.exit(1)
    
    # Step 6: Verify vector DB
    verified = verify_vector_db(token, document_id)
    if verified:
        print_section("SUCCESS!")
        print_success("Book successfully uploaded and saved in vector database!")
        print_info(f"Document ID: {document_id}")
        print_info("You can now use this document for search and worksheet generation")
    else:
        print_error("Verification failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
