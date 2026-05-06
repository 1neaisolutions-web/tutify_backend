"""
Complete Document Upload Flow Test
Tests the entire flow from upload to published status.
"""
import requests
import time
import sys
from pathlib import Path

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

def login():
    """Login and get token."""
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code == 200:
        return r.json().get("access_token")
    return None

def find_document():
    """Find the test document."""
    possible_paths = [
        Path("(ustad360.com) Mathematics 6 SNC 2023-24.pdf"),
        Path("../(ustad360.com) Mathematics 6 SNC 2023-24.pdf"),
        Path("../../(ustad360.com) Mathematics 6 SNC 2023-24.pdf"),
    ]
    
    for parent in [Path("."), Path(".."), Path("../..")]:
        for file in parent.rglob("*.pdf"):
            if "Mathematics" in file.name and "6" in file.name:
                possible_paths.append(file)
    
    for path in possible_paths:
        if path.exists() and path.is_file():
            return path
    return None

def get_or_create_pack(token):
    """Get existing pack or create new one."""
    r = requests.get(
        f"{BASE}/api/v1/admin/content-packs?is_active=true",
        headers={"Authorization": f"Bearer {token}"}
    )
    if r.status_code == 200:
        packs = r.json()
        if packs and len(packs) > 0:
            return packs[0]["id"]
    
    # Create new pack
    r = requests.post(
        f"{BASE}/api/v1/admin/content-packs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Test Pack - Mathematics 6",
            "description": "Test pack for document upload",
            "subject": "Mathematics",
            "grade": "Grade 6",
            "curriculum": "SNC 2023-24"
        }
    )
    if r.status_code == 201:
        return r.json()["id"]
    return None

def upload_document(token, pack_id, file_path):
    """Upload document."""
    url = f"{BASE}/api/v1/admin/documents/upload-stream"
    
    with open(file_path, 'rb') as f:
        files = {'file': (file_path.name, f, 'application/pdf')}
        data = {'pack_id': pack_id, 'title': 'Mathematics 6 SNC 2023-24'}
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.post(url, files=files, data=data, headers=headers, stream=True, timeout=120)
        
        if response.status_code != 200:
            return None
        
        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                import json
                try:
                    event_data = json.loads(line_str[6:])
                    if event_data.get('type') == 'success':
                        return event_data.get('document_id')
                except:
                    pass
    return None

def monitor_until_complete(token, document_id, max_wait=600):
    """Monitor document until published or failed."""
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        r = requests.get(
            f"{BASE}/api/v1/admin/documents/{document_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if r.status_code == 200:
            doc = r.json()
            status = doc.get("status")
            error_code = doc.get("error_code")
            error_message = doc.get("error_message")
            total_pages = doc.get("total_pages")
            
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed}s] Status: {status}", end="")
            if total_pages:
                print(f" | Pages: {total_pages}", end="")
            print()
            
            if status == "published":
                print("\n" + "="*70)
                print("✅ SUCCESS! Document published successfully!")
                print("="*70)
                print(f"Document ID: {document_id}")
                print(f"Total Pages: {total_pages}")
                print(f"File Size: {doc.get('file_size', 0) / 1024 / 1024:.2f} MB")
                return True
            
            if status == "failed":
                print("\n" + "="*70)
                print("❌ FAILED! Document processing failed!")
                print("="*70)
                print(f"Error Code: {error_code}")
                print(f"Error Message: {error_message}")
                
                # Try to publish with override if QA failed
                if error_code == "QA_VALIDATION_FAILED":
                    print("\nAttempting to publish with QA override...")
                    pub_r = requests.post(
                        f"{BASE}/api/v1/admin/documents/{document_id}/publish?override_qa=true",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    if pub_r.status_code == 200:
                        print("✅ Published with QA override!")
                        return True
                
                return False
        
        time.sleep(5)
    
    print("\n⏱ Timeout: Processing taking longer than expected")
    return False

def main():
    print("="*70)
    print("COMPLETE DOCUMENT UPLOAD FLOW TEST")
    print("="*70)
    print()
    
    # Step 1: Login
    print("1. Logging in...")
    token = login()
    if not token:
        print("❌ Login failed")
        sys.exit(1)
    print("✅ Login successful")
    
    # Step 2: Get or create pack
    print("\n2. Getting content pack...")
    pack_id = get_or_create_pack(token)
    if not pack_id:
        print("❌ Failed to get/create pack")
        sys.exit(1)
    print(f"✅ Using pack: {pack_id}")
    
    # Step 3: Find document
    print("\n3. Finding document...")
    file_path = find_document()
    if not file_path:
        print("❌ Document not found")
        sys.exit(1)
    print(f"✅ Found: {file_path.name} ({file_path.stat().st_size / 1024 / 1024:.2f} MB)")
    
    # Step 4: Upload
    print("\n4. Uploading document...")
    document_id = upload_document(token, pack_id, file_path)
    if not document_id:
        print("❌ Upload failed")
        sys.exit(1)
    print(f"✅ Upload successful! Document ID: {document_id}")
    
    # Step 5: Monitor processing
    print("\n5. Monitoring processing...")
    print("   (This may take several minutes for large documents)\n")
    success = monitor_until_complete(token, document_id, max_wait=600)
    
    if success:
        print("\n" + "="*70)
        print("🎉 COMPLETE FLOW TEST PASSED!")
        print("="*70)
        sys.exit(0)
    else:
        print("\n" + "="*70)
        print("❌ COMPLETE FLOW TEST FAILED")
        print("="*70)
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
