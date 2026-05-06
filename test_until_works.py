"""Test endpoints repeatedly until they work."""
import requests
import time
import sys

BASE = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

def test_health():
    """Test health endpoint."""
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        return r.status_code == 200
    except:
        return False

def login():
    """Login and get token."""
    try:
        r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10)
        if r.status_code == 200:
            return r.json().get("access_token")
    except:
        pass
    return None

def test_list_packs(token):
    """Test list content packs endpoint."""
    try:
        r = requests.get(
            f"{BASE}/api/v1/admin/content-packs?is_active=true",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if r.status_code == 200:
            return True, "SUCCESS"
        elif r.status_code == 500:
            error = r.json().get("error", "")
            if "institution_admin" in error:
                return False, "ENUM_ERROR"
            else:
                return False, f"OTHER_ERROR: {error[:100]}"
        else:
            return False, f"STATUS_{r.status_code}"
    except Exception as e:
        return False, f"EXCEPTION: {str(e)[:100]}"

print("=" * 70)
print("TESTING UNTIL IT WORKS")
print("=" * 70)

# Wait for server
print("\n1. Waiting for server to start...")
for i in range(30):
    if test_health():
        print(f"   OK: Server is running")
        break
    time.sleep(1)
    if i % 5 == 0:
        print(f"   Waiting... ({i+1}/30)")
else:
    print("   ERROR: Server not responding")
    sys.exit(1)

# Login
print("\n2. Logging in...")
token = None
for i in range(10):
    token = login()
    if token:
        print(f"   OK: Login successful")
        break
    time.sleep(2)
    if i % 2 == 0:
        print(f"   Retrying login... ({i+1}/10)")

if not token:
    print("   ERROR: Login failed")
    sys.exit(1)

# Test endpoint repeatedly
print("\n3. Testing list endpoint (will retry until it works)...")
max_attempts = 20
for attempt in range(1, max_attempts + 1):
    success, result = test_list_packs(token)
    
    if success:
        print(f"\n{'='*70}")
        print("SUCCESS! Endpoint is working!")
        print(f"{'='*70}")
        sys.exit(0)
    else:
        if result == "ENUM_ERROR":
            print(f"   Attempt {attempt}/{max_attempts}: FAILED - Enum error (institution_admin still in SQL)")
        else:
            print(f"   Attempt {attempt}/{max_attempts}: FAILED - {result}")
        
        if attempt < max_attempts:
            print(f"   Waiting 3 seconds before retry...")
            time.sleep(3)
        else:
            print(f"\n{'='*70}")
            print(f"FAILED after {max_attempts} attempts")
            print(f"Last error: {result}")
            print(f"{'='*70}")
            sys.exit(1)
