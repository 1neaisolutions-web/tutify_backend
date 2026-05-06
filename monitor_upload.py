"""Monitor document upload and processing until completion."""
import requests
import time
import sys

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"
DOCUMENT_ID = "8114a121-bedf-4e3a-acd9-10d46d716c6c"

def login():
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code == 200:
        return r.json().get("access_token")
    return None

def get_status(token):
    r = requests.get(f"{BASE}/api/v1/admin/documents/{DOCUMENT_ID}", headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 200:
        return r.json()
    return None

print("=" * 70)
print("MONITORING DOCUMENT PROCESSING")
print("=" * 70)
print(f"Document ID: {DOCUMENT_ID}\n")

token = login()
if not token:
    print("❌ Failed to login")
    sys.exit(1)

print("Monitoring status (checking every 5 seconds)...\n")

for i in range(120):  # Monitor for 10 minutes
    doc = get_status(token)
    if not doc:
        print(f"[{i*5}s] Failed to get status")
        time.sleep(5)
        continue
    
    status = doc.get("status")
    error_code = doc.get("error_code")
    error_message = doc.get("error_message")
    remediation_hint = doc.get("remediation_hint")
    total_pages = doc.get("total_pages")
    
    print(f"[{i*5}s] Status: {status}", end="")
    if total_pages:
        print(f" | Pages: {total_pages}", end="")
    if error_code:
        print(f" | Error: {error_code}", end="")
    print()
    
    if status == "published":
        print("\n" + "=" * 70)
        print("✅ SUCCESS! Document processing completed!")
        print("=" * 70)
        print(f"Total Pages: {total_pages}")
        sys.exit(0)
    
    if status == "failed":
        print("\n" + "=" * 70)
        print("❌ FAILED! Document processing failed!")
        print("=" * 70)
        if error_code:
            print(f"Error Code: {error_code}")
        if error_message:
            print(f"Error Message: {error_message}")
        if remediation_hint:
            print(f"Remediation: {remediation_hint}")
        print("=" * 70)
        
        # If it failed, try to retry
        print("\nAttempting to retry...")
        retry_r = requests.post(
            f"{BASE}/api/v1/admin/documents/{DOCUMENT_ID}/retry",
            headers={"Authorization": f"Bearer {token}"}
        )
        if retry_r.status_code == 200:
            print("✓ Retry initiated. Continuing monitoring...")
            time.sleep(10)  # Wait a bit before checking again
        else:
            print(f"✗ Retry failed: {retry_r.status_code}")
            sys.exit(1)
    
    time.sleep(5)

print("\n" + "=" * 70)
print("⏱ Timeout: Processing is taking longer than expected")
print("=" * 70)
print("Document may still be processing. Check status manually.")
