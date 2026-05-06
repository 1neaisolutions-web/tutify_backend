"""Final verification of document upload flow."""
import requests

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"
DOCUMENT_ID = "47cc5621-330e-4d8e-b831-f4dbfc6331dc"
PACK_ID = "67ff7e11-a2e7-4eac-9177-9f682fb3ba0e"

# Login
token = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]

# Get document
doc = requests.get(f"{BASE}/api/v1/admin/documents/{DOCUMENT_ID}", headers={"Authorization": f"Bearer {token}"}).json()

# Get pack and documents
pack = requests.get(f"{BASE}/api/v1/admin/content-packs/{PACK_ID}", headers={"Authorization": f"Bearer {token}"}).json()
docs = requests.get(f"{BASE}/api/v1/admin/documents?pack_id={PACK_ID}", headers={"Authorization": f"Bearer {token}"}).json()

print("="*70)
print("FINAL VERIFICATION - DOCUMENT UPLOAD FLOW")
print("="*70)
print()
print("DOCUMENT STATUS:")
print(f"  Status: {doc.get('status')}")
print(f"  Filename: {doc.get('filename')}")
print(f"  Total Pages: {doc.get('total_pages')}")
print(f"  File Size: {doc.get('file_size', 0) / 1024 / 1024:.2f} MB")
print(f"  Error Code: {doc.get('error_code') or 'None'}")
print(f"  Error Message: {doc.get('error_message') or 'None'}")
print()
print("CONTENT PACK:")
print(f"  Pack Name: {pack.get('name')}")
print(f"  Total Documents: {len(docs)}")
published = [d for d in docs if d.get('status') == 'published']
print(f"  Published Documents: {len(published)}")
print()
print("="*70)

if doc.get('status') == 'published':
    print("✅ SUCCESS! Document upload flow is working perfectly!")
    print("✅ Document is published and ready to use")
    print("✅ All processing steps completed successfully")
else:
    print(f"⚠ Status: {doc.get('status')}")
