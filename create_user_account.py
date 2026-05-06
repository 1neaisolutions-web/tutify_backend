"""Script to create the new user account with admin privileges."""
import requests
import sys

BASE = "http://127.0.0.1:8000"

# Existing admin credentials
ADMIN_EMAIL = "owais.naseer.dev@gmail.com"
ADMIN_PASSWORD = "123456789aA!"

# New user to create
NEW_EMAIL = "owaais.naseer.dev@gmail.com"
NEW_PASSWORD = "123456789aA!"

def login(email, password):
    """Login and get token."""
    r = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": email, "password": password}
    )
    if r.status_code == 200:
        return r.json().get("access_token")
    return None

def create_user(token, email, password, first_name, last_name, role_name):
    """Create a new user."""
    r = requests.post(
        f"{BASE}/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
            "role_name": role_name,
            "phone": None,
            "username": None
        }
    )
    return r.status_code, r.json() if r.status_code < 300 else r.text

print("=" * 70)
print("Creating New User Account")
print("=" * 70)
print()

# Step 1: Login as admin
print("1. Logging in as admin...")
admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
if not admin_token:
    print("❌ Failed to login as admin")
    sys.exit(1)
print("✓ Admin login successful")

# Step 2: Create new user
print(f"\n2. Creating user: {NEW_EMAIL}")
status, response = create_user(
    admin_token,
    NEW_EMAIL,
    NEW_PASSWORD,
    "Owais",
    "Naseer",
    "org_admin"  # Give org_admin role for content pack access
)

if status == 201:
    print(f"✓ User created successfully!")
    print(f"  Email: {NEW_EMAIL}")
    print(f"  Role: org_admin")
elif status == 400 and "already exists" in str(response).lower():
    print(f"⚠ User already exists")
    print("  Attempting login with new credentials...")
    new_token = login(NEW_EMAIL, NEW_PASSWORD)
    if new_token:
        print("✓ Login successful - account exists and is active")
    else:
        print("❌ Account exists but login failed - check password")
else:
    print(f"❌ Failed to create user: {status}")
    print(f"Response: {response}")
    sys.exit(1)

print("\n" + "=" * 70)
print("Setup Complete!")
print("=" * 70)
