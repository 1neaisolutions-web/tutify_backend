"""
Test all content ingestion endpoints locally.
Run this while the backend is running on http://127.0.0.1:8000
"""
import requests
import json
from typing import Optional

BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")

def print_error(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.END}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.END}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.END}")

def test_endpoint(method: str, path: str, expected_status: int = 200, 
                  headers: Optional[dict] = None, data: Optional[dict] = None,
                  description: str = ""):
    """Test a single endpoint."""
    url = f"{API_BASE}{path}"
    print(f"\n{Colors.BOLD}Testing: {method} {path}{Colors.END}")
    if description:
        print(f"  Description: {description}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=5)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=5)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=5)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=5)
        else:
            print_error(f"Unsupported method: {method}")
            return False
        
        status_ok = response.status_code == expected_status
        if status_ok:
            print_success(f"Status: {response.status_code} (expected {expected_status})")
            try:
                result = response.json()
                print_info(f"Response: {json.dumps(result, indent=2)[:200]}...")
            except:
                print_info(f"Response: {response.text[:200]}")
            return True
        else:
            print_error(f"Status: {response.status_code} (expected {expected_status})")
            try:
                error = response.json()
                print_error(f"Error: {json.dumps(error, indent=2)}")
            except:
                print_error(f"Error: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print_error(f"Connection failed - Is backend running on {BASE_URL}?")
        return False
    except requests.exceptions.Timeout:
        print_error("Request timeout")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

def main():
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}Content Ingestion Endpoints Local Test{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    
    # Test 1: Health check
    print(f"\n{Colors.BOLD}1. Health Check{Colors.END}")
    test_endpoint("GET", "/health", expected_status=200, 
                  description="Backend health check")
    
    # Test 2: Test endpoint (no auth)
    print(f"\n{Colors.BOLD}2. Test Endpoint (No Auth Required){Colors.END}")
    test_endpoint("GET", "/admin/content-packs/test", expected_status=200,
                  description="Test endpoint to verify route registration")
    
    # Test 3: List routes endpoint
    print(f"\n{Colors.BOLD}3. List All Routes{Colors.END}")
    test_endpoint("GET", "/routes", expected_status=200,
                  description="List all registered routes")
    
    # Test 4: Content packs list (requires auth - will fail but should be 401/403, not 404)
    print(f"\n{Colors.BOLD}4. List Content Packs (Requires Auth){Colors.END}")
    result = test_endpoint("GET", "/admin/content-packs?is_active=true", 
                          expected_status=401,  # Should be 401 (no auth) or 403 (wrong role), NOT 404
                          description="List content packs - should return 401/403, not 404")
    
    if result:
        print_success("Endpoint exists! (401/403 is expected without auth)")
    else:
        # Check if it's 404
        try:
            response = requests.get(f"{API_BASE}/admin/content-packs?is_active=true", timeout=5)
            if response.status_code == 404:
                print_error("❌ CRITICAL: Endpoint returns 404 - Route not registered!")
                print_warning("Check if backend has restarted with new code")
            elif response.status_code in [401, 403]:
                print_success("✅ Endpoint exists! (401/403 is expected without auth)")
        except:
            pass
    
    # Test 5: Create content pack (requires auth)
    print(f"\n{Colors.BOLD}5. Create Content Pack (Requires Auth){Colors.END}")
    test_endpoint("POST", "/admin/content-packs", expected_status=401,
                  data={"name": "Test Pack"},
                  description="Create content pack - should return 401/403, not 404")
    
    # Test 6: Get single content pack (requires auth)
    print(f"\n{Colors.BOLD}6. Get Content Pack (Requires Auth){Colors.END}")
    test_endpoint("GET", "/admin/content-packs/test-id-123", expected_status=401,
                  description="Get single content pack - should return 401/403, not 404")
    
    # Test 7: List documents (requires auth)
    print(f"\n{Colors.BOLD}7. List Documents (Requires Auth){Colors.END}")
    test_endpoint("GET", "/admin/documents", expected_status=401,
                  description="List documents - should return 401/403, not 404")
    
    # Test 8: Upload document stream (requires auth)
    print(f"\n{Colors.BOLD}8. Upload Document Stream (Requires Auth){Colors.END}")
    test_endpoint("POST", "/admin/documents/upload-stream", expected_status=401,
                  description="Upload document stream - should return 401/403, not 404")
    
    # Summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}Test Summary{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print_info("If endpoints return 401/403 (not 404), routes are registered correctly!")
    print_info("If endpoints return 404, routes are NOT registered - check backend logs")
    print_warning("To test with auth, you need a valid Bearer token")
    print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")
    print("1. Check backend logs for 'Content ingestion routes registered successfully'")
    print("2. Visit http://127.0.0.1:8000/docs to see all endpoints")
    print("3. Test with authentication token if you have one")

if __name__ == "__main__":
    main()
