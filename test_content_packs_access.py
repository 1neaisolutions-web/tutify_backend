"""Test content packs access with teacher role."""
import requests
import sys

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

print("=" * 70)
print("TESTING CONTENT PACKS ACCESS")
print("=" * 70)
print()

# Step 1: Login
print("1. Logging in...")
try:
    login_response = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10
    )
    login_response.raise_for_status()
    token = login_response.json()["access_token"]
    print(f"   ✅ Login successful")
    print(f"   Token (first 30 chars): {token[:30]}...")
except Exception as e:
    print(f"   ❌ Login failed: {e}")
    if hasattr(e, 'response') and e.response:
        print(f"   Response: {e.response.text}")
    sys.exit(1)

print()

# Step 2: Get user info to verify roles
print("2. Getting user info...")
try:
    user_response = requests.get(
        f"{BASE}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    user_response.raise_for_status()
    user = user_response.json()
    roles = user.get('roles', [])
    role_names = [r.get('name') if isinstance(r, dict) else str(r) for r in roles]
    print(f"   ✅ User info retrieved")
    print(f"   Email: {user.get('email')}")
    print(f"   Roles: {role_names}")
    
    if 'teacher' not in role_names:
        print()
        print("   ⚠️  WARNING: User does NOT have teacher role!")
        print("   Run: python assign_teacher_role.py")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

print()

# Step 3: Test content packs access
print("3. Testing content packs access...")
print(f"   URL: {BASE}/api/v1/admin/content-packs?is_active=true")
print(f"   Authorization: Bearer {token[:30]}...")
print()

try:
    packs_response = requests.get(
        f"{BASE}/api/v1/admin/content-packs?is_active=true",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        },
        timeout=10
    )
    
    print(f"   Status Code: {packs_response.status_code}")
    
    if packs_response.status_code == 200:
        packs = packs_response.json()
        print(f"   ✅ SUCCESS! Access granted!")
        print(f"   Found {len(packs)} active content packs")
        if packs:
            print(f"   First pack: {packs[0].get('name', 'N/A')}")
    else:
        print(f"   ❌ FAILED! Access denied")
        print(f"   Response: {packs_response.text}")
        print()
        print("   Possible issues:")
        print("   1. Backend server not restarted after code changes")
        print("   2. Route not properly registered")
        print("   3. Role check failing in backend")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    if hasattr(e, 'response') and e.response:
        print(f"   Status: {e.response.status_code}")
        print(f"   Response: {e.response.text}")

print()
print("=" * 70)
