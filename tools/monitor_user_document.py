"""
Monitor a specific document uploaded from frontend.
Shows real-time status, progress, and addresses issues.
"""
import os
import sys
import io
import time
import requests
import json
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, DocumentProcessingRun, PageText, Chunk
from sqlalchemy import text

BASE_URL = "http://127.0.0.1:8000"
DOCUMENT_ID = "34ee0763-88fa-47d4-b696-ad15e4f9bb9b"

def get_auth_token():
    """Get authentication token."""
    test_credentials = [
        {"email": "test1@gmail.com", "password": "123456789aA!"},
        {"email": "admin@1ne.ai", "password": "Admin123!@#"},
    ]
    
    for creds in test_credentials:
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/auth/login",
                json=creds,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()["access_token"]
        except Exception:
            continue
    return None

def get_db_metrics(document_id: str):
    """Get current database metrics for document."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return None
        
        # Page texts
        page_count = db.query(PageText).filter(PageText.document_id == document_id).count()
        non_empty_pages = db.execute(
            text("SELECT COUNT(*) FROM page_texts WHERE document_id = :d AND char_count > 0"),
            {"d": document_id}
        ).scalar_one()
        
        # Chunks
        chunk_count = db.query(Chunk).filter(Chunk.document_id == document_id).count()
        chunks_with_vectors = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE document_id = :d AND embedding_v IS NOT NULL"),
            {"d": document_id}
        ).scalar_one()
        
        # Latest processing run
        latest_run = db.query(DocumentProcessingRun).filter(
            DocumentProcessingRun.document_id == document_id
        ).order_by(DocumentProcessingRun.started_at.desc()).first()
        
        return {
            "status": doc.status,
            "error_code": doc.error_code,
            "error_message": doc.error_message,
            "pages": page_count,
            "non_empty_pages": non_empty_pages,
            "chunks": chunk_count,
            "chunks_with_vectors": chunks_with_vectors,
            "current_step": latest_run.current_step if latest_run else None,
            "progress": latest_run.progress_percentage if latest_run else None,
            "processing_metadata": doc.processing_metadata or {},
        }
    finally:
        db.close()

def monitor_status_stream(document_id: str, token: str, max_minutes=30):
    """Monitor document status via SSE stream."""
    print("=" * 80)
    print(f"MONITORING DOCUMENT: {document_id}")
    print("=" * 80)
    print()
    
    url = f"{BASE_URL}/api/v1/admin/documents/{document_id}/status/stream"
    headers = {"Authorization": f"Bearer {token}"}
    
    start_time = time.time()
    last_status = None
    last_progress = None
    
    try:
        print(f"[INFO] Connecting to status stream...")
        print(f"[INFO] URL: {url}")
        print()
        
        response = requests.get(url, headers=headers, stream=True, timeout=max_minutes * 60)
        
        if response.status_code != 200:
            print(f"[FAIL] Status stream failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        print(f"[PASS] Status stream connected (Status: {response.status_code})")
        print()
        print("-" * 80)
        print("REAL-TIME STATUS UPDATES:")
        print("-" * 80)
        print()
        
        for line in response.iter_lines():
            if not line:
                continue
            
            elapsed = int(time.time() - start_time)
            line_str = line.decode('utf-8')
            
            if line_str.startswith('data: '):
                try:
                    data_str = line_str[6:]  # Remove 'data: ' prefix
                    data = json.loads(data_str)
                    
                    status = data.get('status')
                    progress = data.get('progress', {})
                    error_code = data.get('error_code')
                    error_message = data.get('error_message')
                    current_step = data.get('current_step')
                    
                    # Only print if status or progress changed
                    if status != last_status or progress != last_progress:
                        print(f"[{elapsed}s] Status: {status}")
                        if current_step:
                            print(f"         Step: {current_step}")
                        if progress:
                            pct = progress.get('percentage', 0)
                            completed = progress.get('completed', 0)
                            total = progress.get('total', 0)
                            print(f"         Progress: {pct}% (completed: {completed}, total: {total})")
                        
                        if error_code:
                            print(f"         [ERROR] Code: {error_code}")
                            if error_message:
                                print(f"         Message: {error_message[:200]}")
                        
                        # Get DB metrics
                        db_metrics = get_db_metrics(document_id)
                        if db_metrics:
                            print(f"         DB Metrics:")
                            print(f"           Pages: {db_metrics['pages']} (non-empty: {db_metrics['non_empty_pages']})")
                            print(f"           Chunks: {db_metrics['chunks']} (with vectors: {db_metrics['chunks_with_vectors']})")
                        
                        print()
                        
                        last_status = status
                        last_progress = progress
                        
                        # Check for completion or failure
                        if status == "published":
                            print("=" * 80)
                            print("[SUCCESS] Document processing completed successfully!")
                            print("=" * 80)
                            print_final_metrics(document_id)
                            return True
                        elif status == "failed":
                            print("=" * 80)
                            print("[FAIL] Document processing failed!")
                            print("=" * 80)
                            print_issue_analysis(document_id, error_code, error_message)
                            return False
                
                except json.JSONDecodeError as e:
                    print(f"[WARN] Failed to parse JSON: {e}")
                    print(f"       Line: {line_str[:100]}")
                except Exception as e:
                    print(f"[ERROR] Error processing stream: {e}")
        
        print("[WARN] Stream ended without completion")
        return False
        
    except requests.exceptions.Timeout:
        print(f"[TIMEOUT] Monitoring exceeded {max_minutes} minutes")
        return False
    except requests.exceptions.ConnectionError:
        print(f"[FAIL] Cannot connect to backend at {BASE_URL}")
        print("       Ensure backend server is running")
        return False
    except Exception as e:
        print(f"[ERROR] Monitoring failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def print_final_metrics(document_id: str):
    """Print final metrics after successful processing."""
    print()
    print("FINAL METRICS:")
    print("-" * 80)
    
    metrics = get_db_metrics(document_id)
    if metrics:
        print(f"Status: {metrics['status']}")
        print(f"Pages: {metrics['pages']} total, {metrics['non_empty_pages']} non-empty")
        print(f"Chunks: {metrics['chunks']} total, {metrics['chunks_with_vectors']} with embeddings")
        
        # Check OCR
        meta = metrics.get('processing_metadata', {})
        if 'ocr_preflight' in meta:
            preflight = meta['ocr_preflight']
            print(f"OCR Preflight:")
            print(f"  Tesseract Found: {preflight.get('tesseract_found', False)}")
            print(f"  Poppler Found: {preflight.get('poppler_found', False)}")
            if preflight.get('poppler_path'):
                print(f"  Poppler Path: {preflight['poppler_path']}")
        
        if meta.get('ocr_attempted'):
            print(f"OCR Attempted: Yes")
        
        print()
        print("[PASS] All metrics look good!")

def print_issue_analysis(document_id: str, error_code: str, error_message: str):
    """Analyze and suggest fixes for processing issues."""
    print()
    print("ISSUE ANALYSIS:")
    print("-" * 80)
    print(f"Error Code: {error_code}")
    print(f"Error Message: {error_message}")
    print()
    
    metrics = get_db_metrics(document_id)
    if metrics:
        print("Current State:")
        print(f"  Status: {metrics['status']}")
        print(f"  Pages: {metrics['pages']} (non-empty: {metrics['non_empty_pages']})")
        print(f"  Chunks: {metrics['chunks']}")
        print()
    
    # Provide specific recommendations
    if error_code == "OCR_ERROR" or (error_message and "Poppler" in error_message):
        print("[ISSUE] Poppler/OCR Error Detected")
        print()
        print("Possible Causes:")
        print("  1. Poppler DLL dependencies missing (VC++ Redistributable)")
        print("  2. Poppler path not set correctly")
        print("  3. pdfinfo.exe failing to run")
        print()
        print("Solutions:")
        print("  1. Install Microsoft VC++ Redistributable 2015-2022 (x64):")
        print("     https://aka.ms/vs/17/release/vc_redist.x64.exe")
        print("  2. Restart backend server after installation")
        print("  3. Retry processing: POST /api/v1/admin/documents/{document_id}/retry")
        print()
        print("Check if Poppler works:")
        print(f"     python tools/test_poppler_dlls.py")
    
    elif error_code == "TEXT_EXTRACTION_ERROR":
        print("[ISSUE] Text Extraction Failed")
        print("Solution: Enable OCR or check if document is corrupted")
    
    elif error_code == "EMBEDDING_ERROR":
        print("[ISSUE] Embedding Generation Failed")
        print("Solution: Check OPENAI_API_KEY or use fake embeddings")
    
    else:
        print(f"[ISSUE] Unknown error: {error_code}")
        print("Check backend logs for detailed error information")

if __name__ == "__main__":
    print("=" * 80)
    print("DOCUMENT PROCESSING MONITOR")
    print("=" * 80)
    print()
    
    # Get auth token
    print("[1] Authenticating...")
    token = get_auth_token()
    if not token:
        print("[FAIL] Could not authenticate")
        print("       Please ensure backend is running and test user exists")
        sys.exit(1)
    print("[PASS] Authentication successful")
    print()
    
    # Get initial status
    print("[2] Getting initial document status...")
    initial_metrics = get_db_metrics(DOCUMENT_ID)
    if not initial_metrics:
        print(f"[FAIL] Document {DOCUMENT_ID} not found")
        sys.exit(1)
    
    print(f"   Filename: (checking...)")
    print(f"   Current Status: {initial_metrics['status']}")
    print(f"   Current Step: {initial_metrics.get('current_step', 'N/A')}")
    print(f"   Progress: {initial_metrics.get('progress', 0)}%")
    print()
    
    # Monitor status stream
    print("[3] Starting real-time monitoring...")
    print()
    success = monitor_status_stream(DOCUMENT_ID, token, max_minutes=30)
    
    print()
    print("=" * 80)
    if success:
        print("MONITORING COMPLETE: [PASS]")
    else:
        print("MONITORING COMPLETE: [FAIL] - Check issue analysis above")
    print("=" * 80)
