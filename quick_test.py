"""Quick test of endpoints."""
import requests
import json

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

print("=" * 60)
print("QUICK ENDPOINT TEST")
print("=" * 60)

# Login
print("\n1. Login...")
try:
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10)
    if r.status_code == 200:
        token = r.json().get("access_token")
        print(f"   OK: Got token")
    else:
        print(f"   FAILED: {r.status_code}")
        print(f"   {r.text[:200]}")
        exit(1)
except Exception as e:
    print(f"   ERROR: {e}")
    exit(1)

# Test list endpoint
print("\n2. Test List Content Packs...")
try:
    r = requests.get(
        f"{BASE}/api/v1/admin/content-packs?is_active=true",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"   OK: Got {len(data.get('items', []))} packs")
    elif r.status_code == 500:
        error = r.json().get("error", "")
        if "institution_admin" in error:
            print(f"   FAILED: Still using institution_admin in SQL!")
            print(f"   Error: {error[:300]}")
        else:
            print(f"   FAILED: {error[:200]}")
    else:
        print(f"   Status: {r.status_code}")
        print(f"   Response: {r.text[:200]}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 60)
print("Test complete")
print("=" * 60)
