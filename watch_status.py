"""
Watch document processing status in real-time.
Shows progress, current step, and updates continuously.
"""
import requests
import time
import sys
from datetime import datetime

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

def login():
    """Login."""
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code == 200:
        return r.json().get("access_token")
    return None

def get_status(token, doc_id):
    """Get document status."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/api/v1/admin/documents/{doc_id}", headers=headers, timeout=10)
    if r.status_code == 200:
        return r.json()
    return None

def main():
    if len(sys.argv) > 1:
        doc_id = sys.argv[1]
    else:
        doc_id = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"
    
    print("\n" + "="*70)
    print("DOCUMENT STATUS MONITOR")
    print("="*70)
    print(f"Document ID: {doc_id}")
    print("Press Ctrl+C to stop")
    print("="*70 + "\n")
    
    token = login()
    if not token:
        print("[FAIL] Login failed")
        sys.exit(1)
    
    start_time = time.time()
    last_status = None
    last_progress = -1
    
    try:
        while True:
            doc = get_status(token, doc_id)
            if not doc:
                print("[WARN] Could not get status")
                time.sleep(5)
                continue
            
            elapsed = time.time() - start_time
            elapsed_str = f"{int(elapsed/60)}m {int(elapsed%60)}s"
            
            status = doc.get('status', 'unknown')
            progress = doc.get('progress_percentage', 0)
            step = doc.get('current_step', '')
            pages = doc.get('total_pages', 0)
            chunks = doc.get('chunks_count', 0)
            vectors = doc.get('vectors_stored', 0)
            error = doc.get('error_message')
            
            # Clear line and print status
            print(f"\r[{elapsed_str}] {status.upper():12} | Progress: {progress:3}% | Pages: {pages:3} | Chunks: {chunks:4} | Vectors: {vectors:4}", end="", flush=True)
            
            if status != last_status:
                print()  # New line for status change
                print(f"  Status changed to: {status.upper()}")
                if step:
                    print(f"  Current step: {step}")
                if error:
                    print(f"  Error: {error}")
                last_status = status
            
            if status == 'published' and chunks > 0 and vectors > 0:
                print("\n")
                print("[PASS] Document is ready!")
                print(f"  Chunks: {chunks}, Vectors: {vectors}")
                break
            elif status == 'failed':
                print("\n")
                print(f"[FAIL] Processing failed: {error}")
                break
            
            time.sleep(3)  # Update every 3 seconds
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Monitoring stopped by user")
    except Exception as e:
        print(f"\n[FAIL] Error: {e}")

if __name__ == "__main__":
    main()
