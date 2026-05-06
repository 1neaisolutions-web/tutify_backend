"""
Check document status and reprocess if needed.
"""
import requests
import sys
from pathlib import Path

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"
DOCUMENT_ID = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"

def login():
    """Login and get token."""
    r = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30
    )
    if r.status_code == 200:
        return r.json().get("access_token")
    return None

def check_document(token, doc_id):
    """Check document status."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"{BASE}/api/v1/admin/documents/{doc_id}",
        headers=headers,
        timeout=10
    )
    if r.status_code == 200:
        return r.json()
    return None

def reprocess_document(token, doc_id):
    """Trigger document reprocessing."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE}/api/v1/admin/documents/{doc_id}/retry",
        headers=headers,
        timeout=10
    )
    return r.status_code == 200

def main():
    token = login()
    if not token:
        print("Login failed")
        sys.exit(1)
    
    doc = check_document(token, DOCUMENT_ID)
    if not doc:
        print("Could not get document")
        sys.exit(1)
    
    print(f"Document Status: {doc.get('status')}")
    print(f"Total Pages: {doc.get('total_pages', 0)}")
    print(f"Chunks: {doc.get('chunks_count', 0)}")
    print(f"Vectors: {doc.get('vectors_stored', 0)}")
    print(f"Error: {doc.get('error_message', 'None')}")
    print(f"Force OCR: {doc.get('processing_metadata', {}).get('force_ocr', False)}")
    
    if doc.get('chunks_count', 0) == 0:
        print("\nNo chunks found. Triggering reprocessing...")
        if reprocess_document(token, DOCUMENT_ID):
            print("Reprocessing triggered successfully")
        else:
            print("Failed to trigger reprocessing")

if __name__ == "__main__":
    main()
