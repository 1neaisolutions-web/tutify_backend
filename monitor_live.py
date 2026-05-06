"""
Live monitoring dashboard for document processing.
Shows real-time status, progress, and current step.
Runs continuously until document is fully processed and verified.
"""
import requests
import time
import sys
import os
from datetime import datetime

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

def clear_screen():
    """Clear screen (works on Windows and Unix)."""
    os.system('cls' if os.name == 'nt' else 'clear')

def login():
    """Login and get token."""
    try:
        r = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=30
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except:
        pass
    return None

def get_status(token, doc_id):
    """Get document status."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE}/api/v1/admin/documents/{doc_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def format_time(seconds):
    """Format elapsed time."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    else:
        hours = int(seconds/3600)
        mins = int((seconds%3600)/60)
        return f"{hours}h {mins}m"

def print_dashboard(doc, elapsed, token, doc_id):
    """Print monitoring dashboard."""
    clear_screen()
    
    print("="*70)
    print("DOCUMENT PROCESSING MONITOR - LIVE DASHBOARD")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Elapsed: {format_time(elapsed)}")
    print("="*70)
    print()
    
    if not doc:
        print("[WARN] Could not get document status")
        print("       Backend may be processing...")
        return
    
    status = doc.get('status', 'unknown')
    progress = doc.get('progress_percentage', 0)
    step = doc.get('current_step', '')
    pages = doc.get('total_pages', 0)
    chunks = doc.get('chunks_count', 0)
    vectors = doc.get('vectors_stored', 0)
    error = doc.get('error_message', '')
    error_code = doc.get('error_code', '')
    
    # Status
    status_colors = {
        'uploaded': 'INFO',
        'text_extracting': 'INFO',
        'ocr_running': 'INFO',
        'normalizing': 'INFO',
        'chunking': 'INFO',
        'embedding': 'INFO',
        'indexing': 'INFO',
        'qa_validation': 'INFO',
        'published': 'PASS',
        'failed': 'FAIL'
    }
    status_display = status_colors.get(status, 'INFO')
    
    print(f"STATUS: {status.upper()}")
    if step and step != status:
        print(f"STEP:   {step}")
    print()
    
    # Progress bar
    bar_width = 50
    filled = int(bar_width * progress / 100)
    bar = "=" * filled + "-" * (bar_width - filled)
    print(f"PROGRESS: [{bar}] {progress}%")
    print()
    
    # Details
    print("DETAILS:")
    print(f"  Pages:     {pages}")
    print(f"  Chunks:    {chunks}")
    print(f"  Vectors:   {vectors}")
    print()
    
    # Processing steps
    steps = {
        'uploaded': '✓ Uploaded',
        'text_extracting': '→ Extracting text...',
        'ocr_running': '→ Running OCR (this takes 15-30 min)...',
        'normalizing': '→ Normalizing text...',
        'chunking': '→ Creating chunks...',
        'embedding': '→ Generating embeddings...',
        'indexing': '→ Storing in vector DB...',
        'qa_validation': '→ Running QA validation...',
        'published': '✓ Published',
        'failed': '✗ Failed'
    }
    
    print("PROCESSING STEPS:")
    for step_name, step_display in steps.items():
        if step_name == status:
            print(f"  {step_display} <-- CURRENT")
        elif status in ['published', 'failed'] and step_name == status:
            print(f"  {step_display}")
        else:
            print(f"  {step_display.replace('→', ' ').replace('✓', ' ').replace('✗', ' ')}")
    print()
    
    # Error info
    if error:
        print("ERROR:")
        print(f"  Code: {error_code}")
        print(f"  Message: {error}")
        print()
    
    # Completion check
    if status == 'published':
        if chunks > 0 and vectors > 0:
            print("="*70)
            print("✓ SUCCESS - DOCUMENT READY")
            print("="*70)
            print(f"Chunks: {chunks}, Vectors: {vectors}")
            print("Ready for worksheet generation!")
            print("="*70)
        else:
            print("="*70)
            print("✗ WARNING - PUBLISHED BUT NO CHUNKS")
            print("="*70)
            print("Document marked as published but has no chunks/vectors")
            print("This should not happen - document needs reprocessing")
            print("="*70)
    elif status == 'failed':
        print("="*70)
        print("✗ FAILED")
        print("="*70)
        print(f"Error: {error}")
        print("="*70)
    
    print()
    print("Press Ctrl+C to stop monitoring")
    print("="*70)

def main():
    """Main monitoring loop."""
    if len(sys.argv) > 1:
        doc_id = sys.argv[1]
    else:
        doc_id = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"
    
    print("\n[INFO] Logging in...")
    token = login()
    if not token:
        print("[FAIL] Login failed")
        sys.exit(1)
    print("[PASS] Logged in\n")
    
    start_time = time.time()
    last_status = None
    consecutive_errors = 0
    
    try:
        while True:
            elapsed = time.time() - start_time
            
            doc = get_status(token, doc_id)
            
            if doc:
                status = doc.get('status', 'unknown')
                consecutive_errors = 0
                
                print_dashboard(doc, elapsed, token, doc_id)
                
                # Check if complete
                if status == 'published':
                    chunks = doc.get('chunks_count', 0)
                    vectors = doc.get('vectors_stored', 0)
                    if chunks > 0 and vectors > 0:
                        print("\n[PASS] Monitoring complete - document is ready!")
                        break
                    else:
                        print("\n[WARN] Published but no chunks - waiting for processing...")
                elif status == 'failed':
                    error = doc.get('error_message', 'Unknown error')
                    print(f"\n[FAIL] Processing failed: {error}")
                    print("[INFO] Check error message above")
                    print("[INFO] You may need to reprocess the document")
                    break
                
                last_status = status
            else:
                consecutive_errors += 1
                if consecutive_errors > 10:
                    print("\n[FAIL] Too many connection errors - stopping")
                    break
                print(f"\r[WARN] Could not get status (attempt {consecutive_errors})...", end="", flush=True)
            
            time.sleep(3)  # Update every 3 seconds
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Monitoring stopped by user")
    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
