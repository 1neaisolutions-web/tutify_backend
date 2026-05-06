"""
Real-time document processing monitor with progress tracking.
Shows status updates, progress percentage, and current step.
Monitors until document is fully processed and verified.
"""
import requests
import time
import sys
from datetime import datetime
from typing import Optional, Dict, Any

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

def login() -> Optional[str]:
    """Login and get token."""
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=30
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception as e:
        print(f"[FAIL] Login failed: {e}")
    return None

def get_document_status(token: str, document_id: str) -> Optional[Dict[str, Any]]:
    """Get document status."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(
            f"{BASE}/api/v1/admin/documents/{document_id}",
            headers=headers,
            timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[WARN] Failed to get status: {e}")
    return None

def get_status_stream(token: str, document_id: str):
    """Get real-time status stream."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE}/api/v1/admin/documents/{document_id}/status/stream"
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=300)
        if r.status_code == 200:
            return r
    except Exception as e:
        print(f"[WARN] Stream failed: {e}")
    return None

def format_time(seconds: float) -> str:
    """Format elapsed time."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    else:
        hours = int(seconds/3600)
        mins = int((seconds%3600)/60)
        return f"{hours}h {mins}m"

def print_status_bar(percentage: int, width: int = 50):
    """Print progress bar."""
    filled = int(width * percentage / 100)
    bar = "=" * filled + "-" * (width - filled)
    print(f"  [{bar}] {percentage}%", end="\r")

def monitor_document(token: str, document_id: str, max_wait_minutes: int = 120):
    """Monitor document processing with real-time updates."""
    print("\n" + "="*70)
    print("DOCUMENT PROCESSING MONITOR")
    print("="*70)
    print(f"Document ID: {document_id}")
    print(f"Max wait time: {max_wait_minutes} minutes")
    print("="*70 + "\n")
    
    start_time = time.time()
    last_status = None
    last_progress = -1
    last_step = None
    
    # Try to use SSE stream first
    stream = get_status_stream(token, document_id)
    
    if stream:
        print("[INFO] Using real-time status stream...\n")
        import json
        
        for line in stream.iter_lines():
            if not line:
                continue
            
            elapsed = time.time() - start_time
            line_str = line.decode('utf-8')
            
            if line_str.startswith('data: '):
                try:
                    data_str = line_str[6:].strip()
                    status_data = json.loads(data_str)
                    
                    current_status = status_data.get('status', 'unknown')
                    current_step = status_data.get('current_step', '')
                    progress = status_data.get('progress', {})
                    percentage = progress.get('percentage', 0) if progress else 0
                    
                    # Print status changes
                    if current_status != last_status or current_step != last_step:
                        print(f"\n[{format_time(elapsed)}] Status: {current_status.upper()}")
                        if current_step:
                            print(f"         Step: {current_step}")
                        last_status = current_status
                        last_step = current_step
                    
                    # Print progress updates
                    if percentage != last_progress and percentage > 0:
                        print_status_bar(percentage)
                        last_progress = percentage
                    
                    # Check for completion
                    if current_status == 'published':
                        print("\n")
                        print("[PASS] Document published!")
                        return True
                    elif current_status == 'failed':
                        print("\n")
                        error = status_data.get('error_message', 'Unknown error')
                        print(f"[FAIL] Processing failed: {error}")
                        return False
                        
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    print(f"\n[WARN] Error parsing stream: {e}")
    else:
        # Fallback to polling
        print("[INFO] Using polling mode (checking every 5 seconds)...\n")
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_minutes * 60:
                print(f"\n[FAIL] Timeout after {max_wait_minutes} minutes")
                return False
            
            doc = get_document_status(token, document_id)
            if not doc:
                time.sleep(5)
                continue
            
            status = doc.get('status', 'unknown')
            progress = doc.get('progress_percentage', 0)
            step = doc.get('current_step', '')
            
            # Print status changes
            if status != last_status or step != last_step:
                print(f"\n[{format_time(elapsed)}] Status: {status.upper()}")
                if step:
                    print(f"         Step: {step}")
                if progress > 0:
                    print_status_bar(progress)
                last_status = status
                last_step = step
            elif progress != last_progress and progress > 0:
                print_status_bar(progress)
                last_progress = progress
            
            # Check for completion
            if status == 'published':
                print("\n")
                chunks = doc.get('chunks_count', 0)
                vectors = doc.get('vectors_stored', 0)
                print(f"[PASS] Document published!")
                print(f"         Chunks: {chunks}, Vectors: {vectors}")
                
                if chunks > 0 and vectors > 0:
                    return True
                else:
                    print(f"[FAIL] Published but no chunks/vectors!")
                    return False
            elif status == 'failed':
                print("\n")
                error = doc.get('error_message', 'Unknown error')
                print(f"[FAIL] Processing failed: {error}")
                return False
            
            time.sleep(5)  # Poll every 5 seconds
    
    return False

def verify_document(token: str, document_id: str) -> bool:
    """Verify document is fully processed."""
    print("\n" + "="*70)
    print("FINAL VERIFICATION")
    print("="*70 + "\n")
    
    doc = get_document_status(token, document_id)
    if not doc:
        print("[FAIL] Could not get document status")
        return False
    
    status = doc.get('status', 'unknown')
    pages = doc.get('total_pages', 0)
    chunks = doc.get('chunks_count', 0)
    vectors = doc.get('vectors_stored', 0)
    error = doc.get('error_message')
    
    print(f"Status: {status}")
    print(f"Pages: {pages}")
    print(f"Chunks: {chunks}")
    print(f"Vectors: {vectors}")
    if error:
        print(f"Error: {error}")
    print()
    
    if status == 'published' and chunks > 0 and vectors > 0:
        print("[PASS] Document is ready for worksheet generation!")
        print(f"[PASS] {chunks} chunks with embeddings stored")
        return True
    elif status == 'failed':
        print("[FAIL] Document processing failed")
        return False
    else:
        print("[WARN] Document not fully processed")
        return False

def main():
    """Main monitoring function."""
    if len(sys.argv) > 1:
        document_id = sys.argv[1]
    else:
        document_id = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"  # Default document
    
    print("\n" + "="*70)
    print("DOCUMENT PROCESSING MONITOR")
    print("="*70)
    print(f"Monitoring document: {document_id}")
    print("="*70)
    
    # Login
    print("\n[INFO] Logging in...")
    token = login()
    if not token:
        print("[FAIL] Authentication failed")
        sys.exit(1)
    print("[PASS] Logged in successfully\n")
    
    # Monitor processing
    success = monitor_document(token, document_id, max_wait_minutes=120)
    
    if not success:
        print("\n[FAIL] Processing did not complete successfully")
        print("[INFO] Check error message above for details")
        sys.exit(1)
    
    # Verify final status
    verified = verify_document(token, document_id)
    
    if verified:
        print("\n" + "="*70)
        print("SUCCESS - DOCUMENT READY")
        print("="*70)
        print(f"Document ID: {document_id}")
        print("Status: Published with chunks and embeddings")
        print("Ready for: Worksheet generation, Search, Q&A")
        print("="*70 + "\n")
    else:
        print("\n[FAIL] Verification failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
