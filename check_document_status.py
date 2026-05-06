"""Quick script to check document status."""
import requests
import time
import sys

BASE = "http://127.0.0.1:8000"
EMAIL = "owaais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"
DOCUMENT_ID = "96524a17-61ce-4a52-a85e-87b7ec658308"

# Login
token = requests.post(
    f"{BASE}/api/v1/auth/login",
    json={"email": EMAIL, "password": PASSWORD}
).json()["access_token"]

print(f"Monitoring document: {DOCUMENT_ID}\n")

for i in range(60):  # Monitor for 5 minutes
    r = requests.get(
        f"{BASE}/api/v1/admin/documents/{DOCUMENT_ID}",
        headers={"Authorization": f"Bearer {token}"}
    )
    doc = r.json()
    status = doc.get("status")
    error_code = doc.get("error_code")
    error_message = doc.get("error_message")
    total_pages = doc.get("total_pages")
    
    print(f"[{i*5}s] Status: {status}", end="")
    if total_pages:
        print(f" | Pages: {total_pages}", end="")
    if error_code:
        print(f" | Error: {error_code}", end="")
    if error_message:
        print(f" | {error_message[:50]}", end="")
    print()
    
    if status in ["published", "failed"]:
        if status == "published":
            print("\n✓ Document processing completed successfully!")
        else:
            print(f"\n✗ Document processing failed!")
            print(f"Error Code: {error_code}")
            print(f"Error Message: {error_message}")
        break
    
    time.sleep(5)
