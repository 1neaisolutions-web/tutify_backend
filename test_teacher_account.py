"""Test teacher account access to content packs."""
import requests
import sys

BASE = "http://127.0.0.1:8000"
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"

print("=" * 70)
print("TESTING TEACHER ACCOUNT ACCESS")
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
    if login_response.status_code != 200:
        print(f"   ❌ Login failed!")
        print(f"   Status: {login_response.status_code}")
        print(f"   Response: {login_response.text}")
        sys.exit(1)
    
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
    print(f"   User ID: {user.get('id')}")
    print(f"   Tenant ID: {user.get('tenant_id')}")
    print(f"   Roles: {role_names}")
    
    if 'teacher' not in role_names:
        print()
        print("   ⚠️  WARNING: User does NOT have teacher role!")
        print("   Will assign teacher role now...")
        needs_role = True
    else:
        print("   ✅ User HAS teacher role!")
        needs_role = False
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

print()

# Step 3: Assign teacher role if needed
if needs_role:
    print("3. Assigning teacher role...")
    from sqlalchemy.orm import Session
    from app.db.session import SessionLocal
    from app.domains.auth.models import User, Role, UserRole, RoleName
    
    db: Session = SessionLocal()
    try:
        # Get user
        db_user = db.query(User).filter(User.email == EMAIL.lower()).first()
        if not db_user:
            print(f"   ❌ User not found in database: {EMAIL}")
            sys.exit(1)
        
        # Get teacher role
        teacher_role = db.query(Role).filter(Role.name == RoleName.TEACHER).first()
        if not teacher_role:
            print("   ❌ Teacher role not found in database!")
            sys.exit(1)
        
        # Check if already has role
        existing = db.query(UserRole).filter(
            UserRole.user_id == db_user.id,
            UserRole.role_id == teacher_role.id,
            UserRole.tenant_id == db_user.tenant_id
        ).first()
        
        if existing:
            print("   ✅ User already has teacher role (database check)")
        else:
            # Assign teacher role
            new_user_role = UserRole(
                user_id=db_user.id,
                role_id=teacher_role.id,
                tenant_id=db_user.tenant_id,
                granted_by=None
            )
            db.add(new_user_role)
            db.commit()
            print("   ✅ Teacher role assigned successfully!")
        
        db.close()
    except Exception as e:
        print(f"   ❌ Error assigning role: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        db.close()
        sys.exit(1)
    
    # Re-login to get fresh token with updated roles
    print()
    print("   Re-logging in to get fresh token...")
    try:
        login_response = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=10
        )
        login_response.raise_for_status()
        token = login_response.json()["access_token"]
        print("   ✅ Re-login successful")
    except Exception as e:
        print(f"   ❌ Re-login failed: {e}")
        sys.exit(1)

print()

# Step 4: Test content packs access
print("4. Testing content packs access...")
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
            for i, pack in enumerate(packs[:3], 1):
                print(f"   Pack {i}: {pack.get('name', 'N/A')}")
    else:
        print(f"   ❌ FAILED! Access denied")
        print(f"   Response: {packs_response.text}")
        print()
        print("   Possible issues:")
        print("   1. Backend server not restarted after code changes")
        print("   2. User still doesn't have teacher role")
        print("   3. Token expired - try logging out and back in")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    if hasattr(e, 'response') and e.response:
        print(f"   Status: {e.response.status_code}")
        print(f"   Response: {e.response.text}")

print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
