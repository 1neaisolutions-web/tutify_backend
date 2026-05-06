"""Check if a user has the teacher role assigned."""
import requests
import sys

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"  # Change this to the teacher's email
PASSWORD = "123456789aA!"

print("=" * 70)
print("TEACHER ROLE VERIFICATION")
print("=" * 70)
print()

# Step 1: Login
print(f"1. Logging in as {EMAIL}...")
try:
    login_response = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10
    )
    login_response.raise_for_status()
    token = login_response.json()["access_token"]
    print(f"   ✅ Login successful")
    print(f"   Token: {token[:20]}...")
except Exception as e:
    print(f"   ❌ Login failed: {e}")
    sys.exit(1)

print()

# Step 2: Get current user info
print("2. Getting current user info...")
try:
    user_response = requests.get(
        f"{BASE}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    user_response.raise_for_status()
    user = user_response.json()
    print(f"   ✅ User info retrieved")
    print(f"   User ID: {user.get('id')}")
    print(f"   Email: {user.get('email')}")
    print(f"   Tenant ID: {user.get('tenant_id')}")
    print(f"   Roles: {user.get('roles', [])}")
except Exception as e:
    print(f"   ❌ Failed to get user info: {e}")
    print(f"   Response: {user_response.text if 'user_response' in locals() else 'N/A'}")
    sys.exit(1)

print()

# Step 3: Try to access content packs
print("3. Testing content packs access...")
try:
    packs_response = requests.get(
        f"{BASE}/api/v1/admin/content-packs?is_active=true",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    if packs_response.status_code == 200:
        packs = packs_response.json()
        print(f"   ✅ Access granted!")
        print(f"   Found {len(packs)} active content packs")
    else:
        print(f"   ❌ Access denied")
        print(f"   Status: {packs_response.status_code}")
        print(f"   Response: {packs_response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    if 'packs_response' in locals():
        print(f"   Status: {packs_response.status_code}")
        print(f"   Response: {packs_response.text}")

print()
print("=" * 70)
print("DIAGNOSIS:")
print("=" * 70)

if 'user' in locals():
    roles = user.get('roles', [])
    role_names = [r.get('name', '') if isinstance(r, dict) else str(r) for r in roles]
    
    if 'teacher' in role_names or 'TEACHER' in role_names:
        print("✅ User HAS teacher role assigned")
        print("   If access is still denied, check:")
        print("   1. Backend server restarted after code changes?")
        print("   2. Tenant ID matches between user and content packs?")
    else:
        print("❌ User DOES NOT have teacher role assigned")
        print(f"   Current roles: {role_names}")
        print("   SOLUTION: Assign teacher role to this user in the database")
        print()
        print("   To assign teacher role, run this SQL:")
        print(f"   -- First, get the teacher role ID:")
        print(f"   SELECT id, name FROM roles WHERE name = 'teacher';")
        print()
        print(f"   -- Then assign it to the user:")
        print(f"   INSERT INTO user_roles (id, user_id, role_id, tenant_id, granted_at)")
        print(f"   SELECT gen_random_uuid(), '{user.get('id')}', r.id, '{user.get('tenant_id')}', NOW()")
        print(f"   FROM roles r WHERE r.name = 'teacher'")
        print(f"   ON CONFLICT DO NOTHING;")

print("=" * 70)
