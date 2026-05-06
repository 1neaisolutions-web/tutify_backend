"""
Simple verification script - checks route registration without external dependencies.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("Backend Setup Verification")
print("=" * 60)
print()

try:
    # Check 1: Import routes
    print("1. Checking route imports...")
    from app.domains.content_ingestion.routes import router as content_router
    print("   ✅ Content ingestion routes imported")
    print(f"   Router prefix: {content_router.prefix}")
    print()
    
    # Check 2: Count routes
    print("2. Counting routes...")
    route_count = 0
    for route in content_router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            route_count += 1
    print(f"   ✅ Found {route_count} routes in content ingestion router")
    print()
    
    # Check 3: Check v1 router
    print("3. Checking v1 router registration...")
    from app.api.v1 import router as v1_router
    v1_routes = [r for r in v1_router.routes if hasattr(r, 'path') and '/admin/content-packs' in str(r.path)]
    if v1_routes:
        print(f"   ✅ Content ingestion routes found in v1 router ({len(v1_routes)} routes)")
    else:
        print("   ❌ Content ingestion routes NOT in v1 router!")
    print()
    
    # Check 4: Check main app
    print("4. Checking main app registration...")
    from app.main import app
    app_routes = [r for r in app.routes if hasattr(r, 'path') and '/admin/content-packs' in str(r.path)]
    if app_routes:
        print(f"   ✅ Content ingestion routes found in main app ({len(app_routes)} routes)")
        print("   ✅ Routes are properly registered!")
    else:
        print("   ❌ Content ingestion routes NOT in main app!")
        print("   ❌ Routes will NOT be accessible!")
    print()
    
    print("=" * 60)
    if app_routes:
        print("✅ SUCCESS: All routes are properly registered!")
        print("   You can start the server with: .\\start_server.ps1")
    else:
        print("❌ ERROR: Routes are not registered in main app!")
    print("=" * 60)
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're in the backend directory")
    print("and all dependencies are installed: pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
