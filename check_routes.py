"""
Quick script to check if content ingestion routes are registered.
Run this to verify routes are available before deploying.
"""
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.main import app
    from app.domains.content_ingestion.routes import router as content_router
    
    print("=" * 60)
    print("Route Registration Check")
    print("=" * 60)
    print()
    
    # Check if router is registered
    print(f"Content ingestion router prefix: {content_router.prefix}")
    print(f"Content ingestion router tags: {content_router.tags}")
    print()
    
    # List all routes in the content ingestion router
    print("Content Ingestion Routes:")
    for route in content_router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            methods = list(route.methods) if route.methods else ['*']
            print(f"  {methods} {route.path}")
    print()
    
    # Check if router is included in main app
    print("Checking if router is included in main app...")
    content_routes_found = False
    for route in app.routes:
        if hasattr(route, 'path'):
            if '/admin/content-packs' in route.path:
                content_routes_found = True
                methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ['*']
                print(f"  ✅ Found: {methods} {route.path}")
    
    if not content_routes_found:
        print("  ❌ Content ingestion routes NOT found in main app!")
        print("     This means the routes are not registered.")
    else:
        print("  ✅ Content ingestion routes are registered!")
    print()
    
    # List all /api/v1/admin routes
    print("All /api/v1/admin routes:")
    admin_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and '/api/v1/admin' in route.path:
            methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ['*']
            admin_routes.append(f"  {methods} {route.path}")
    
    if admin_routes:
        for route in sorted(admin_routes):
            print(route)
    else:
        print("  No /api/v1/admin routes found")
    print()
    
    print("=" * 60)
    print("Check complete!")
    print("=" * 60)
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the backend directory")
    print("and all dependencies are installed.")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
