"""
Quick verification script to check if routes are registered.
Run this to verify routes before testing endpoints.
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("=" * 60)
    print("Verifying Route Registration")
    print("=" * 60)
    print()
    
    # Try importing the router
    print("1. Importing content ingestion routes...")
    from app.domains.content_ingestion.routes import router as content_router
    print("   ✅ Routes module imported successfully")
    print(f"   Router prefix: {content_router.prefix}")
    print(f"   Router tags: {content_router.tags}")
    print()
    
    # Count routes
    print("2. Counting routes in content ingestion router...")
    route_count = 0
    for route in content_router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            route_count += 1
            methods = list(route.methods) if route.methods else ['*']
            print(f"   - {methods} {route.path}")
    print(f"   ✅ Found {route_count} routes")
    print()
    
    # Check if router is registered in v1 router
    print("3. Checking v1 router registration...")
    from app.api.v1 import router as v1_router
    v1_routes = [r for r in v1_router.routes if hasattr(r, 'path') and '/admin/content-packs' in str(r.path)]
    if v1_routes:
        print(f"   ✅ Content ingestion routes found in v1 router ({len(v1_routes)} routes)")
        for route in v1_routes[:5]:  # Show first 5
            methods = list(route.methods) if hasattr(route, 'methods') and route.methods else ['*']
            print(f"      - {methods} {route.path}")
        if len(v1_routes) > 5:
            print(f"      ... and {len(v1_routes) - 5} more")
    else:
        print("   ❌ Content ingestion routes NOT found in v1 router!")
    print()
    
    # Check main app
    print("4. Checking main app registration...")
    from app.main import app
    app_routes = [r for r in app.routes if hasattr(r, 'path') and '/admin/content-packs' in str(r.path)]
    if app_routes:
        print(f"   ✅ Content ingestion routes found in main app ({len(app_routes)} routes)")
    else:
        print("   ❌ Content ingestion routes NOT found in main app!")
        print("   This means routes won't be accessible!")
    print()
    
    print("=" * 60)
    if app_routes:
        print("✅ SUCCESS: Routes are properly registered!")
        print("   You can now start the server and test endpoints.")
    else:
        print("❌ ERROR: Routes are NOT registered in main app!")
        print("   Check app/api/v1/__init__.py and app/main.py")
    print("=" * 60)
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're in the backend directory and dependencies are installed")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
