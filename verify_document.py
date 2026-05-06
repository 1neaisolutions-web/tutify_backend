"""Verify document status."""
import requests

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"
DOCUMENT_ID = "8114a121-bedf-4e3a-acd9-10d46d716c6c"

token = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]
doc = requests.get(f"{BASE}/api/v1/admin/documents/{DOCUMENT_ID}", headers={"Authorization": f"Bearer {token}"}).json()

print("="*70)
print("DOCUMENT STATUS VERIFICATION")
print("="*70)
print(f"Status: {doc.get('status')}")
print(f"Filename: {doc.get('filename')}")
print(f"Total Pages: {doc.get('total_pages')}")
print(f"File Size: {doc.get('file_size', 0) / 1024 / 1024:.2f} MB")
print(f"Processed At: {doc.get('processed_at')}")
print("="*70)

if doc.get('status') == 'published':
    print("\n✅ DOCUMENT SUCCESSFULLY PUBLISHED!")
else:
    print(f"\n⚠ Status: {doc.get('status')}")
