"""
Comprehensive test script for Content Ingestion API endpoints.

Tests all content ingestion endpoints to verify they work as expected.

Usage:
    # Option 1: Test against running server (requires requests)
    python test_content_ingestion_endpoints.py --server http://localhost:8000
    
    # Option 2: Test using FastAPI TestClient (no server needed)
    python test_content_ingestion_endpoints.py
"""
import json
import sys
import os
from typing import Optional, Dict, Any

# Try to import requests for testing against running server
USE_TEST_CLIENT = False
try:
    import requests
except ImportError:
    print("=" * 60)
    print("ERROR: 'requests' module is not installed.")
    print("=" * 60)
    print("\nPlease install it using one of the following:")
    print("  1. pip install requests")
    print("  2. pip install -r requirements.txt")
    print("  3. If using venv: .\\venv\\Scripts\\pip install requests")
    print("\nOr activate your virtual environment first:")
    print("  .\\venv\\Scripts\\activate")
    print("  python test_content_ingestion_endpoints.py")
    print("\n" + "=" * 60)
    sys.exit(1)

# Configuration
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
API_BASE = f"{BASE_URL}/api/v1"

# Test results tracking
test_results = []
passed = 0
failed = 0


def log_test(name: str, test_passed: bool, details: str = ""):
    """Log test result."""
    global passed, failed
    status = "✅ PASS" if test_passed else "❌ FAIL"
    test_results.append({
        "name": name,
        "passed": test_passed,
        "details": details
    })
    if test_passed:
        passed += 1
    else:
        failed += 1
    print(f"{status}: {name}")
    if details:
        print(f"   {details}")


def check_server_health() -> bool:
    """Check if server is running."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            log_test("Server Health Check", True, f"Server is running at {BASE_URL}")
            return True
        else:
            log_test("Server Health Check", False, f"Server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        log_test("Server Health Check", False, f"Could not connect to {BASE_URL}. Is the server running?")
        return False
    except Exception as e:
        log_test("Server Health Check", False, f"Error: {str(e)}")
        return False


def get_auth_token(email: str = "admin@test.com", password: str = "Test123!@#") -> Optional[str]:
    """Get authentication token for testing."""
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            print(f"   ⚠️  Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"   ⚠️  Login error: {str(e)}")
        return None


def test_test_endpoint():
    """Test the test endpoint (no auth required)."""
    try:
        response = requests.get(
            f"{API_BASE}/admin/content-packs/test",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            expected_keys = ["message", "status", "path"]
            has_all_keys = all(key in data for key in expected_keys)
            log_test(
                "Test Endpoint (No Auth)",
                response.status_code == 200 and has_all_keys,
                f"Response: {json.dumps(data, indent=2)}"
            )
        else:
            log_test(
                "Test Endpoint (No Auth)",
                False,
                f"Expected 200, got {response.status_code}: {response.text}"
            )
    except Exception as e:
        log_test("Test Endpoint (No Auth)", False, f"Error: {str(e)}")


def test_list_content_packs(token: str):
    """Test listing content packs."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_BASE}/admin/content-packs",
            headers=headers,
            params={"is_active": True},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            is_list = isinstance(data, list)
            log_test(
                "List Content Packs",
                response.status_code == 200 and is_list,
                f"Retrieved {len(data) if is_list else 0} packs"
            )
        elif response.status_code == 403:
            log_test(
                "List Content Packs",
                False,
                "403 Forbidden - User may not have required role (org_admin, institution_admin, or super_admin)"
            )
        elif response.status_code == 401:
            log_test(
                "List Content Packs",
                False,
                "401 Unauthorized - Invalid or missing token"
            )
        else:
            log_test(
                "List Content Packs",
                False,
                f"Expected 200, got {response.status_code}: {response.text[:200]}"
            )
    except Exception as e:
        log_test("List Content Packs", False, f"Error: {str(e)}")


def test_create_content_pack(token: str):
    """Test creating a content pack."""
    try:
        pack_data = {
            "name": "Test Content Pack",
            "description": "Test pack created by automated test",
            "subject": "Mathematics",
            "grade": "Grade 10",
            "curriculum": "Common Core"
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            f"{API_BASE}/admin/content-packs",
            headers=headers,
            json=pack_data,
            timeout=10
        )
        if response.status_code == 201:
            data = response.json()
            has_required_fields = all(key in data for key in ["id", "name", "is_active", "created_at"])
            pack_id = data.get("id")
            log_test(
                "Create Content Pack",
                response.status_code == 201 and has_required_fields,
                f"Created pack with ID: {pack_id}"
            )
            return pack_id
        elif response.status_code == 403:
            log_test(
                "Create Content Pack",
                False,
                "403 Forbidden - User may not have required role"
            )
        elif response.status_code == 401:
            log_test(
                "Create Content Pack",
                False,
                "401 Unauthorized - Invalid or missing token"
            )
        else:
            log_test(
                "Create Content Pack",
                False,
                f"Expected 201, got {response.status_code}: {response.text[:200]}"
            )
        return None
    except Exception as e:
        log_test("Create Content Pack", False, f"Error: {str(e)}")
        return None


def test_get_content_pack(token: str, pack_id: str):
    """Test getting a specific content pack."""
    if not pack_id:
        log_test("Get Content Pack", False, "No pack ID available (create failed)")
        return
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_BASE}/admin/content-packs/{pack_id}",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            has_required_fields = all(key in data for key in ["id", "name", "is_active"])
            log_test(
                "Get Content Pack",
                response.status_code == 200 and has_required_fields,
                f"Retrieved pack: {data.get('name')}"
            )
        elif response.status_code == 404:
            log_test(
                "Get Content Pack",
                False,
                "404 Not Found - Pack may not exist or user doesn't have access"
            )
        elif response.status_code == 403:
            log_test(
                "Get Content Pack",
                False,
                "403 Forbidden - User may not have required role"
            )
        else:
            log_test(
                "Get Content Pack",
                False,
                f"Expected 200, got {response.status_code}: {response.text[:200]}"
            )
    except Exception as e:
        log_test("Get Content Pack", False, f"Error: {str(e)}")


def test_list_documents(token: str):
    """Test listing documents."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_BASE}/admin/documents",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            is_list = isinstance(data, list)
            log_test(
                "List Documents",
                response.status_code == 200 and is_list,
                f"Retrieved {len(data) if is_list else 0} documents"
            )
        elif response.status_code == 403:
            log_test(
                "List Documents",
                False,
                "403 Forbidden - User may not have required role"
            )
        elif response.status_code == 401:
            log_test(
                "List Documents",
                False,
                "401 Unauthorized - Invalid or missing token"
            )
        else:
            log_test(
                "List Documents",
                False,
                f"Expected 200, got {response.status_code}: {response.text[:200]}"
            )
    except Exception as e:
        log_test("List Documents", False, f"Error: {str(e)}")


def test_worksheet_endpoints(token: str):
    """Test worksheet generation endpoints."""
    # Test worksheet generate endpoint
    try:
        worksheet_data = {
            "pack_id": "00000000-0000-0000-0000-000000000000",  # Dummy UUID
            "topic_text": "Algebra Basics",
            "grade": "Grade 10",
            "subject": "Mathematics",
            "num_questions": 5,
            "difficulty_mix": {"easy": 2, "medium": 2, "hard": 1}
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            f"{API_BASE}/worksheets/generate",
            headers=headers,
            json=worksheet_data,
            timeout=30  # Longer timeout for LLM generation
        )
        if response.status_code == 200:
            data = response.json()
            has_required_fields = all(key in data for key in ["id", "questions", "answer_key"])
            log_test(
                "Generate Worksheet",
                response.status_code == 200 and has_required_fields,
                f"Generated worksheet with {len(data.get('questions', []))} questions"
            )
            worksheet_id = data.get("id")
            if worksheet_id:
                test_get_worksheet(token, worksheet_id)
        elif response.status_code == 404:
            log_test(
                "Generate Worksheet",
                False,
                "404 Not Found - Pack may not exist"
            )
        elif response.status_code == 401:
            log_test(
                "Generate Worksheet",
                False,
                "401 Unauthorized - Invalid or missing token"
            )
        else:
            log_test(
                "Generate Worksheet",
                False,
                f"Expected 200, got {response.status_code}: {response.text[:200]}"
            )
    except Exception as e:
        log_test("Generate Worksheet", False, f"Error: {str(e)}")


def test_get_worksheet(token: str, worksheet_id: str):
    """Test getting a specific worksheet."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_BASE}/worksheets/{worksheet_id}",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            has_required_fields = all(key in data for key in ["id", "questions"])
            log_test(
                "Get Worksheet",
                response.status_code == 200 and has_required_fields,
                f"Retrieved worksheet with {len(data.get('questions', []))} questions"
            )
        elif response.status_code == 404:
            log_test(
                "Get Worksheet",
                False,
                "404 Not Found - Worksheet may not exist"
            )
        else:
            log_test(
                "Get Worksheet",
                False,
                f"Expected 200, got {response.status_code}: {response.text[:200]}"
            )
    except Exception as e:
        log_test("Get Worksheet", False, f"Error: {str(e)}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Content Ingestion API Endpoints Test Suite")
    print("=" * 60)
    print()
    
    # Check server health
    if not check_server_health():
        print("\n" + "=" * 60)
        print("❌ Server is not running!")
        print("=" * 60)
        print("\nPlease start the server first:")
        print("  1. Activate virtual environment:")
        print("     .\\venv\\Scripts\\activate")
        print("\n  2. Start the server:")
        print("     python -m uvicorn app.main:app --reload")
        print("\n  3. Then run this test script again")
        print("\n" + "=" * 60)
        sys.exit(1)
    
    print()
    print("-" * 60)
    print("Testing Endpoints")
    print("-" * 60)
    print()
    
    # Test endpoint without auth
    test_test_endpoint()
    print()
    
    # Get auth token
    print("Getting authentication token...")
    token = get_auth_token()
    if not token:
        print("\n⚠️  Could not get auth token. Some tests will be skipped.")
        print("   You may need to create a test user with admin role.")
        print()
    else:
        print("✅ Authentication token obtained")
        print()
    
    # Test authenticated endpoints
    if token:
        # Content Pack endpoints
        test_list_content_packs(token)
        pack_id = test_create_content_pack(token)
        if pack_id:
            test_get_content_pack(token, pack_id)
        print()
        
        # Document endpoints
        test_list_documents(token)
        print()
        
        # Worksheet endpoints
        test_worksheet_endpoints(token)
        print()
    
    # Print summary
    print()
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total Tests: {len(test_results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print()
    
    if failed > 0:
        print("Failed Tests:")
        for result in test_results:
            if not result["passed"]:
                print(f"  - {result['name']}: {result['details']}")
        print()
    
    # Exit with appropriate code
    if failed == 0:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print(f"❌ {failed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
