"""
Comprehensive Document Upload Diagnostic and Test Script
Tests document upload flow, monitors processing, and identifies failures.
"""
import requests
import time
import sys
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"  # Using existing admin account
PASSWORD = "123456789aA!"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_section(title: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")

def print_success(msg: str):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_error(msg: str):
    """Print error message."""
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_warning(msg: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")

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
            timeout=30  # Increased timeout
        )
        if r.status_code == 200:
            token = r.json().get("access_token")
            print_success(f"Login successful")
            return token
        else:
            print_error(f"Login failed: {r.status_code} - {r.text}")
            # Try to provide helpful error message
            if r.status_code == 401:
                print_warning("Invalid credentials. Please verify:")
                print_warning(f"  - Email: {EMAIL}")
                print_warning("  - Password is correct")
                print_warning("  - Account exists in the database")
    except Exception as e:
        print_error(f"Login exception: {e}")
    return None

def check_environment() -> Dict[str, Any]:
    """Check environment configuration."""
    print_section("1. Checking Environment Configuration")
    
    issues = []
    config = {}
    
    # Check OpenAI API Key
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        print_success("OPENAI_API_KEY is set")
        config["OPENAI_API_KEY"] = "***" + openai_key[-4:] if len(openai_key) > 4 else "***"
    else:
        print_error("OPENAI_API_KEY is NOT set (required for embeddings)")
        issues.append("Set OPENAI_API_KEY in .env file")
    
    # Check OCR Engine
    ocr_engine = os.getenv("OCR_ENGINE", "tesseract")
    print_info(f"OCR_ENGINE: {ocr_engine}")
    config["OCR_ENGINE"] = ocr_engine
    
    # Check Embedding Provider
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "openai")
    print_info(f"EMBEDDING_PROVIDER: {embedding_provider}")
    config["EMBEDDING_PROVIDER"] = embedding_provider
    
    # Check Vector Store
    vector_store = os.getenv("VECTOR_STORE", "pgvector")
    print_info(f"VECTOR_STORE: {vector_store}")
    config["VECTOR_STORE"] = vector_store
    
    # Check Documents Directory
    documents_dir = os.getenv("DOCUMENTS_DIR", "uploads/documents")
    print_info(f"DOCUMENTS_DIR: {documents_dir}")
    if not os.path.exists(documents_dir):
        print_warning(f"Documents directory does not exist: {documents_dir}")
        print_info("Will be created automatically on first upload")
    else:
        print_success(f"Documents directory exists: {documents_dir}")
    config["DOCUMENTS_DIR"] = documents_dir
    
    # Check Tesseract (if using tesseract OCR)
    if ocr_engine == "tesseract":
        try:
            import pytesseract
            version = pytesseract.get_tesseract_version()
            print_success(f"Tesseract OCR is installed (version {version})")
        except Exception as e:
            print_error(f"Tesseract OCR not available: {e}")
            issues.append("Install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki")
    
    return {"config": config, "issues": issues}

def get_or_create_pack(token: str) -> Optional[str]:
    """Get existing pack or create a new one."""
    print_section("2. Getting or Creating Content Pack")
    
    # First, try to get existing packs
    try:
        r = requests.get(
            f"{BASE}/api/v1/admin/content-packs?is_active=true",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if r.status_code == 200:
            packs = r.json()
            if packs and len(packs) > 0:
                pack_id = packs[0]["id"]
                print_success(f"Using existing pack: {packs[0]['name']} ({pack_id})")
                return pack_id
    except Exception as e:
        print_warning(f"Could not fetch existing packs: {e}")
    
    # Create a new pack
    print_info("Creating new content pack...")
    try:
        r = requests.post(
            f"{BASE}/api/v1/admin/content-packs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Test Pack - Mathematics 6",
                "description": "Test pack for document upload diagnostic",
                "subject": "Mathematics",
                "grade": "Grade 6",
                "curriculum": "SNC 2023-24"
            },
            timeout=10
        )
        if r.status_code == 201:
            pack = r.json()
            pack_id = pack["id"]
            print_success(f"Created new pack: {pack['name']} ({pack_id})")
            return pack_id
        else:
            print_error(f"Failed to create pack: {r.status_code} - {r.text}")
    except Exception as e:
        print_error(f"Exception creating pack: {e}")
    
    return None

def find_test_document() -> Optional[Path]:
    """Find the test document."""
    print_section("3. Locating Test Document")
    
    # Look for the document in common locations
    possible_paths = [
        Path("Mathematics 6 SNC 2023-24.pdf"),
        Path("../Mathematics 6 SNC 2023-24.pdf"),
        Path("../../Mathematics 6 SNC 2023-24.pdf"),
        Path("uploads/documents/Mathematics 6 SNC 2023-24.pdf"),
    ]
    
    # Also check current directory and parent directories
    for parent in [Path("."), Path(".."), Path("../..")]:
        for file in parent.rglob("*.pdf"):
            if "Mathematics" in file.name and "6" in file.name:
                possible_paths.append(file)
    
    for path in possible_paths:
        if path.exists() and path.is_file():
            print_success(f"Found document: {path.absolute()}")
            print_info(f"File size: {path.stat().st_size / 1024 / 1024:.2f} MB")
            return path
    
    print_error("Could not find 'Mathematics 6 SNC 2023-24.pdf'")
    print_info("Please ensure the file is in the current directory or a parent directory")
    return None

def upload_document(token: str, pack_id: str, file_path: Path) -> Optional[str]:
    """Upload document and return document_id."""
    print_section("4. Uploading Document")
    
    url = f"{BASE}/api/v1/admin/documents/upload-stream"
    
    print_info(f"Uploading: {file_path.name}")
    print_info(f"To pack: {pack_id}")
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/pdf')}
            data = {
                'pack_id': pack_id,
                'title': 'Mathematics 6 SNC 2023-24',
            }
            headers = {'Authorization': f'Bearer {token}'}
            
            print_info("Sending upload request...")
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=headers,
                stream=True,
                timeout=120
            )
            
            if response.status_code != 200:
                print_error(f"Upload failed: {response.status_code}")
                print_error(f"Response: {response.text[:500]}")
                return None
            
            # Parse SSE stream
            document_id = None
            pack_id_returned = None
            
            print_info("Monitoring upload progress...")
            for line in response.iter_lines():
                if not line:
                    continue
                
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    try:
                        event_data = json.loads(line_str[6:])
                        event_type = event_data.get('type')
                        
                        if event_type == 'progress':
                            step = event_data.get('step', '')
                            message = event_data.get('message', '')
                            percentage = event_data.get('percentage', 0)
                            print_info(f"  [{percentage}%] {step}: {message}")
                            
                        elif event_type == 'success':
                            document_id = event_data.get('document_id')
                            pack_id_returned = event_data.get('pack_id')
                            message = event_data.get('message', '')
                            print_success(f"Upload successful: {message}")
                            print_info(f"Document ID: {document_id}")
                            break
                            
                        elif event_type == 'error':
                            error_msg = event_data.get('message', 'Unknown error')
                            print_error(f"Upload error: {error_msg}")
                            return None
                            
                    except json.JSONDecodeError as e:
                        print_warning(f"Could not parse SSE event: {e}")
                        print_warning(f"Raw line: {line_str[:100]}")
            
            if document_id:
                return document_id
            else:
                print_error("Upload completed but no document_id returned")
                return None
                
    except Exception as e:
        print_error(f"Upload exception: {e}")
        import traceback
        traceback.print_exc()
        return None

def monitor_processing(token: str, document_id: str, max_wait: int = 300):
    """Monitor document processing status."""
    print_section("5. Monitoring Document Processing")
    
    url = f"{BASE}/api/v1/admin/documents/{document_id}/status/stream"
    headers = {'Authorization': f'Bearer {token}'}
    
    print_info(f"Monitoring document: {document_id}")
    print_info(f"Max wait time: {max_wait} seconds")
    print_info("Waiting for processing to complete...\n")
    
    start_time = time.time()
    last_status = None
    last_step = None
    connection_drops = 0
    max_connection_drops = 5
    
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=max_wait + 10)
        
        if response.status_code != 200:
            print_error(f"Status stream failed: {response.status_code}")
            print_error(f"Response: {response.text[:500]}")
            return False
        
        for line in response.iter_lines():
            if not line:
                continue
            
            elapsed = int(time.time() - start_time)
            
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                try:
                    status_data = json.loads(line_str[6:])
                    current_status = status_data.get('status')
                    current_step = status_data.get('current_step')
                    progress = status_data.get('progress', {})
                    error_code = status_data.get('error_code')
                    error_message = status_data.get('error_message')
                    remediation_hint = status_data.get('remediation_hint')
                    
                    # Only print when status changes
                    if current_status != last_status or current_step != last_step:
                        if progress:
                            percentage = progress.get('percentage', 0)
                            step = progress.get('step', current_step)
                            print_info(f"[{elapsed}s] Status: {current_status} | Step: {step} | Progress: {percentage}%")
                        else:
                            print_info(f"[{elapsed}s] Status: {current_status} | Step: {current_step}")
                        
                        last_status = current_status
                        last_step = current_step
                    
                    # Check for errors
                    if error_code or error_message:
                        print_error(f"\n{'='*70}")
                        print_error("PROCESSING FAILED!")
                        print_error(f"{'='*70}")
                        print_error(f"Error Code: {error_code}")
                        print_error(f"Error Message: {error_message}")
                        if remediation_hint:
                            print_warning(f"Remediation Hint: {remediation_hint}")
                        print_error(f"{'='*70}\n")
                        return False
                    
                    # Check if completed
                    if current_status == 'published':
                        print_success(f"\n{'='*70}")
                        print_success("DOCUMENT PROCESSING COMPLETED SUCCESSFULLY!")
                        print_success(f"{'='*70}\n")
                        return True
                    
                    # Check if failed
                    if current_status == 'failed':
                        print_error(f"\n{'='*70}")
                        print_error("DOCUMENT PROCESSING FAILED!")
                        print_error(f"{'='*70}")
                        if error_code:
                            print_error(f"Error Code: {error_code}")
                        if error_message:
                            print_error(f"Error Message: {error_message}")
                        if remediation_hint:
                            print_warning(f"Remediation Hint: {remediation_hint}")
                        print_error(f"{'='*70}\n")
                        return False
                    
                    # Timeout check
                    if elapsed > max_wait:
                        print_warning(f"\nProcessing timeout after {max_wait} seconds")
                        print_warning(f"Current status: {current_status}")
                        return False
                        
                except json.JSONDecodeError as e:
                    print_warning(f"Could not parse status event: {e}")
                    print_warning(f"Raw line: {line_str[:100]}")
    
    except requests.exceptions.Timeout:
        print_error(f"Status stream timeout after {max_wait} seconds")
        # Try to get final status
        return check_final_status(token, document_id)
    except requests.exceptions.ChunkedEncodingError:
        print_warning("Connection dropped during streaming. Checking final status...")
        return check_final_status(token, document_id)
    except Exception as e:
        print_warning(f"Status monitoring exception: {e}")
        print_info("Checking final status via API...")
        return check_final_status(token, document_id)
    
    return False

def check_final_status(token: str, document_id: str) -> bool:
    """Check document status via regular API (fallback)."""
    try:
        r = requests.get(
            f"{BASE}/api/v1/admin/documents/{document_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if r.status_code == 200:
            doc = r.json()
            status = doc.get('status')
            error_code = doc.get('error_code')
            error_message = doc.get('error_message')
            remediation_hint = doc.get('remediation_hint')
            
            print_info(f"\nCurrent Status: {status}")
            
            if status == 'published':
                print_success("Document processing completed successfully!")
                return True
            elif status == 'failed':
                print_error(f"\n{'='*70}")
                print_error("DOCUMENT PROCESSING FAILED!")
                print_error(f"{'='*70}")
                if error_code:
                    print_error(f"Error Code: {error_code}")
                if error_message:
                    print_error(f"Error Message: {error_message}")
                if remediation_hint:
                    print_warning(f"Remediation Hint: {remediation_hint}")
                print_error(f"{'='*70}\n")
                return False
            else:
                print_warning(f"Document is still processing (status: {status})")
                print_info("This may take several minutes for large documents.")
                print_info("You can check the status later via the API or frontend.")
                return False
    except Exception as e:
        print_error(f"Failed to check final status: {e}")
        return False

def get_document_details(token: str, document_id: str):
    """Get detailed document information."""
    print_section("6. Document Details")
    
    try:
        r = requests.get(
            f"{BASE}/api/v1/admin/documents/{document_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if r.status_code == 200:
            doc = r.json()
            print_info(f"Filename: {doc.get('filename')}")
            print_info(f"Status: {doc.get('status')}")
            print_info(f"File Size: {doc.get('file_size', 0) / 1024 / 1024:.2f} MB")
            print_info(f"Total Pages: {doc.get('total_pages', 'N/A')}")
            
            if doc.get('error_code'):
                print_error(f"Error Code: {doc.get('error_code')}")
            if doc.get('error_message'):
                print_error(f"Error Message: {doc.get('error_message')}")
            if doc.get('remediation_hint'):
                print_warning(f"Remediation: {doc.get('remediation_hint')}")
        else:
            print_error(f"Failed to get document details: {r.status_code}")
    except Exception as e:
        print_error(f"Exception getting document details: {e}")

def main():
    """Main test flow."""
    print_section("DOCUMENT UPLOAD DIAGNOSTIC TEST")
    print_info(f"Testing upload flow for: Mathematics 6 SNC 2023-24.pdf")
    print_info(f"Backend: {BASE}")
    print_info(f"Email: {EMAIL}\n")
    
    # Step 1: Check health
    print_section("0. Checking Backend Health")
    if not test_health():
        print_error("Backend is not running or not accessible")
        print_info("Please ensure the backend is running on http://127.0.0.1:8000")
        sys.exit(1)
    print_success("Backend is running")
    
    # Step 2: Check environment
    env_check = check_environment()
    if env_check["issues"]:
        print_warning("\nConfiguration Issues Found:")
        for issue in env_check["issues"]:
            print_warning(f"  - {issue}")
        print_info("\nYou can continue, but some features may not work.")
        print_info("Continuing automatically (non-interactive mode)...")
        # Auto-continue in non-interactive mode
        # response = input("\nContinue anyway? (y/n): ")
        # if response.lower() != 'y':
        #     sys.exit(1)
    
    # Step 3: Login
    print_section("1. Authentication")
    token = login()
    if not token:
        print_error("Failed to login")
        sys.exit(1)
    print_success("Login successful")
    
    # Step 4: Get or create pack
    pack_id = get_or_create_pack(token)
    if not pack_id:
        print_error("Failed to get or create content pack")
        sys.exit(1)
    
    # Step 5: Find document
    file_path = find_test_document()
    if not file_path:
        print_error("Test document not found")
        print_info("Please ensure 'Mathematics 6 SNC 2023-24.pdf' is accessible")
        sys.exit(1)
    
    # Step 6: Upload document
    document_id = upload_document(token, pack_id, file_path)
    if not document_id:
        print_error("Document upload failed")
        sys.exit(1)
    
    # Step 7: Monitor processing
    success = monitor_processing(token, document_id, max_wait=300)
    
    # Step 8: Get final details
    get_document_details(token, document_id)
    
    # Final summary
    print_section("TEST SUMMARY")
    if success:
        print_success("✓ Document uploaded and processed successfully!")
        print_success(f"✓ Document ID: {document_id}")
        print_success(f"✓ Pack ID: {pack_id}")
        sys.exit(0)
    else:
        print_error("✗ Document processing failed")
        print_error(f"✗ Document ID: {document_id}")
        print_info("\nCheck the error messages above for details.")
        print_info("Common issues:")
        print_info("  1. Missing OPENAI_API_KEY (required for embeddings)")
        print_info("  2. Tesseract OCR not installed (if OCR is needed)")
        print_info("  3. Database connection issues")
        print_info("  4. File format issues")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
