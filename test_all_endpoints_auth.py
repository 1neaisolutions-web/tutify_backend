"""Test all content ingestion endpoints with authentication."""
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"
EMAIL = "owais.naseer.dev@gmail.com"
PASSWORD = "123456789aA!"

def login():
    """Login and get access token."""
    print("=" * 60)
    print("1. LOGGING IN...")
    print("=" * 60)
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            if token:
                print(f"   OK: Login successful")
                print(f"   Token: {token[:50]}...")
                return token
            else:
                print(f"   ERROR: No access_token in response")
                print(f"   Response: {data}")
                return None
        else:
            print(f"   ERROR: Login failed - Status {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"   ERROR: {e}")
        return None

def test_endpoint(name, method, url, token=None, json_data=None, files=None, expected_status=None):
    """Test a single endpoint."""
    print(f"\n{name}")
    print("-" * 60)
    
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            if files:
                response = requests.post(url, headers=headers, files=files, data=json_data, timeout=30)
            else:
                response = requests.post(url, headers=headers, json=json_data, timeout=10)
        else:
            print(f"   ERROR: Unsupported method {method}")
            return False
        
        status = response.status_code
        print(f"   Status: {status}")
        
        if expected_status:
            if status == expected_status:
                print(f"   OK: Expected status {expected_status}")
                if status == 200 or status == 201:
                    try:
                        data = response.json()
                        print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                    except:
                        print(f"   Response: {response.text[:200]}")
                return True
            else:
                print(f"   ERROR: Expected {expected_status}, got {status}")
                print(f"   Response: {response.text[:500]}")
                return False
        else:
            if status < 400:
                print(f"   OK: Status {status}")
                try:
                    data = response.json()
                    print(f"   Response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                except:
                    print(f"   Response: {response.text[:200]}")
                return True
            else:
                print(f"   ERROR: Status {status}")
                print(f"   Response: {response.text[:500]}")
                return False
                
    except Exception as e:
        print(f"   ERROR: {e}")
        return False

def main():
    print("\n" + "=" * 60)
    print("TESTING ALL CONTENT INGESTION ENDPOINTS")
    print("=" * 60)
    
    # Step 1: Login
    token = login()
    if not token:
        print("\nERROR: Cannot proceed without authentication token")
        sys.exit(1)
    
    # Step 2: Test all endpoints
    print("\n" + "=" * 60)
    print("2. TESTING ENDPOINTS...")
    print("=" * 60)
    
    results = []
    
    # Test endpoints
    results.append(("Health Check", test_endpoint(
        "Health Check",
        "GET",
        f"{BASE_URL}/health",
        expected_status=200
    )))
    
    results.append(("Test Endpoint (no auth)", test_endpoint(
        "Test Endpoint",
        "GET",
        f"{BASE_URL}/api/v1/admin/content-packs/test",
        expected_status=200
    )))
    
    results.append(("List Content Packs", test_endpoint(
        "List Content Packs",
        "GET",
        f"{BASE_URL}/api/v1/admin/content-packs?is_active=true",
        token=token,
        expected_status=200
    )))
    
    results.append(("Create Content Pack", test_endpoint(
        "Create Content Pack",
        "POST",
        f"{BASE_URL}/api/v1/admin/content-packs",
        token=token,
        json_data={
            "name": "Test Pack",
            "description": "Test description",
            "subject": "Mathematics",
            "grade": "Grade 5"
        },
        expected_status=201
    )))
    
    # Get packs to find an ID
    print("\nGetting packs list to find pack_id...")
    try:
        packs_response = requests.get(
            f"{BASE_URL}/api/v1/admin/content-packs?is_active=true",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if packs_response.status_code == 200:
            packs = packs_response.json()
            pack_id = None
            if isinstance(packs, dict) and "items" in packs:
                items = packs["items"]
                if items and len(items) > 0:
                    pack_id = items[0].get("id")
            elif isinstance(packs, list) and len(packs) > 0:
                pack_id = packs[0].get("id")
            
            if pack_id:
                print(f"   Found pack_id: {pack_id}")
                
                results.append(("Get Content Pack", test_endpoint(
                    "Get Content Pack",
                    "GET",
                    f"{BASE_URL}/api/v1/admin/content-packs/{pack_id}",
                    token=token,
                    expected_status=200
                )))
                
                results.append(("List Documents", test_endpoint(
                    "List Documents",
                    "GET",
                    f"{BASE_URL}/api/v1/admin/documents?pack_id={pack_id}",
                    token=token,
                    expected_status=200
                )))
            else:
                print("   No packs found, skipping pack-specific tests")
    except Exception as e:
        print(f"   ERROR getting packs: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"   {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nALL TESTS PASSED!")
        return 0
    else:
        print(f"\n{total - passed} TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
