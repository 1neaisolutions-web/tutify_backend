"""
Comprehensive check script to verify everything is working.
Run this to check backend setup, routes, and connectivity.
"""
import sys
import os
import requests
from pathlib import Path

# Colors for output
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

def check_backend_running():
    """Check if backend is running on localhost:8000"""
    print(f"\n{Colors.BOLD}1. Checking if backend is running...{Colors.END}")
    try:
        response = requests.get("http://127.0.0.1:8000/health", timeout=3)
        if response.status_code == 200:
            print_success("Backend is running on http://127.0.0.1:8000")
            data = response.json()
            print_info(f"Status: {data.get('status', 'unknown')}")
            print_info(f"Database: {data.get('database', 'unknown')}")
            return True
        else:
            print_error(f"Backend responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Backend is NOT running on http://127.0.0.1:8000")
        print_warning("Start backend with: cd 1ne_backend && .\\start_server.ps1")
        return False
    except Exception as e:
        print_error(f"Error checking backend: {e}")
        return False

def check_routes_registered():
    """Check if routes are properly registered"""
    print(f"\n{Colors.BOLD}2. Checking route registration...{Colors.END}")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.main import app
        from app.domains.content_ingestion.routes import router as content_router
        
        # Check content ingestion routes
        app_routes = [r for r in app.routes if hasattr(r, 'path') and '/admin/content-packs' in str(r.path)]
        if app_routes:
            print_success(f"Content ingestion routes registered ({len(app_routes)} routes)")
            return True
        else:
            print_error("Content ingestion routes NOT found in main app")
            return False
    except ImportError as e:
        print_error(f"Import error: {e}")
        print_warning("Make sure you're in the backend directory and dependencies are installed")
        return False
    except Exception as e:
        print_error(f"Error checking routes: {e}")
        return False

def check_test_endpoint():
    """Check if test endpoint works"""
    print(f"\n{Colors.BOLD}3. Testing content packs test endpoint...{Colors.END}")
    try:
        response = requests.get("http://127.0.0.1:8000/api/v1/admin/content-packs/test", timeout=3)
        if response.status_code == 200:
            print_success("Test endpoint is working")
            data = response.json()
            print_info(f"Response: {data.get('message', 'N/A')}")
            return True
        else:
            print_error(f"Test endpoint returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to test endpoint - backend not running")
        return False
    except Exception as e:
        print_error(f"Error testing endpoint: {e}")
        return False

def check_list_endpoint():
    """Check if list endpoint exists (will return 401/403, not 404)"""
    print(f"\n{Colors.BOLD}4. Checking content packs list endpoint...{Colors.END}")
    try:
        response = requests.get("http://127.0.0.1:8000/api/v1/admin/content-packs?is_active=true", timeout=3)
        if response.status_code == 404:
            print_error("Endpoint returns 404 - Route not registered!")
            return False
        elif response.status_code in [401, 403]:
            print_success("Endpoint exists! (401/403 is expected without auth)")
            print_info("This means the route is registered correctly")
            return True
        elif response.status_code == 200:
            print_success("Endpoint works! (You have valid auth)")
            return True
        else:
            print_warning(f"Unexpected status: {response.status_code}")
            return True  # Endpoint exists
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect - backend not running")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def check_frontend_config():
    """Check frontend .env configuration"""
    print(f"\n{Colors.BOLD}5. Checking frontend configuration...{Colors.END}")
    frontend_dir = Path(__file__).parent.parent / "1ne-frontend"
    env_file = frontend_dir / ".env"
    
    if not env_file.exists():
        print_warning(".env file not found in frontend directory")
        print_info("Create 1ne-frontend/.env with: VITE_USE_LOCAL=true")
        return False
    
    try:
        content = env_file.read_text()
        if "VITE_USE_LOCAL=true" in content:
            # Check if Railway URLs are commented out
            if "VITE_API_BASE_URL=https://1nebackend-production" in content and not content.split("VITE_API_BASE_URL=https://1nebackend-production")[0].strip().endswith("#"):
                print_warning("Railway URL is still active in .env")
                print_info("Comment out VITE_API_BASE_URL and VITE_API_URL lines")
                return False
            print_success("Frontend configured for localhost")
            return True
        else:
            print_warning("VITE_USE_LOCAL=true not found in .env")
            print_info("Add VITE_USE_LOCAL=true to 1ne-frontend/.env")
            return False
    except Exception as e:
        print_error(f"Error reading .env: {e}")
        return False

def main():
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}Comprehensive System Check{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    
    results = []
    
    # Check 1: Backend running
    results.append(("Backend Running", check_backend_running()))
    
    # Check 2: Routes registered (only if backend code is accessible)
    try:
        results.append(("Routes Registered", check_routes_registered()))
    except:
        print_warning("Skipping route registration check (backend not accessible)")
        results.append(("Routes Registered", None))
    
    # Check 3: Test endpoint (only if backend is running)
    if results[0][1]:
        results.append(("Test Endpoint", check_test_endpoint()))
        results.append(("List Endpoint", check_list_endpoint()))
    else:
        print_warning("Skipping endpoint tests (backend not running)")
        results.append(("Test Endpoint", None))
        results.append(("List Endpoint", None))
    
    # Check 4: Frontend config
    results.append(("Frontend Config", check_frontend_config()))
    
    # Summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}Summary{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    
    for name, result in results:
        if result is True:
            print_success(f"{name}: OK")
        elif result is False:
            print_error(f"{name}: FAILED")
        else:
            print_warning(f"{name}: SKIPPED")
    
    all_passed = all(r[1] for r in results if r[1] is not None)
    
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    if all_passed:
        print_success("All checks passed! System is ready.")
    else:
        print_error("Some checks failed. See details above.")
        print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")
        if not results[0][1]:
            print("1. Start backend: cd 1ne_backend && .\\start_server.ps1")
        if not results[-1][1]:
            print("2. Configure frontend: Add VITE_USE_LOCAL=true to 1ne-frontend/.env")
            print("3. Restart frontend dev server")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")

if __name__ == "__main__":
    main()
