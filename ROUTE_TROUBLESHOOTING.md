# Route Troubleshooting Guide

## Issue: 404 Not Found on `/api/v1/admin/content-packs`

### Root Cause
The backend on Railway hasn't been restarted with the new code, or there's an import error preventing routes from loading.

### Verification Steps

1. **Check if routes are registered:**
   ```bash
   # Visit FastAPI docs
   https://1nebackend-production.up.railway.app/docs
   
   # Look for "content-ingestion" tag
   # Should see endpoints like:
   # - GET /api/v1/admin/content-packs/test
   # - GET /api/v1/admin/content-packs
   # - POST /api/v1/admin/content-packs
   ```

2. **Test the test endpoint (no auth required):**
   ```bash
   curl https://1nebackend-production.up.railway.app/api/v1/admin/content-packs/test
   ```
   Should return: `{"message": "Content packs route is working", "status": "ok", "path": "/api/v1/admin/content-packs"}`

3. **Check Railway logs:**
   - Go to Railway dashboard
   - Check deployment logs for import errors
   - Look for "Content ingestion routes registered successfully" message

### Solutions

#### Solution 1: Restart Railway Backend
1. Go to Railway dashboard
2. Find your backend service
3. Click "Redeploy" or trigger a new deployment
4. Wait for deployment to complete
5. Test the endpoint again

#### Solution 2: Check for Import Errors
If routes still don't work after restart, check Railway logs for:
- Import errors
- Missing dependencies
- Database connection issues

#### Solution 3: Verify Route Registration
Run the diagnostic script locally:
```bash
cd 1ne_backend
python check_routes.py
```

This will show:
- All registered routes
- Whether content ingestion routes are included
- Any import errors

### Expected Behavior

**Before Fix:**
- `GET /api/v1/admin/content-packs?is_active=true` → 404 Not Found

**After Fix:**
- `GET /api/v1/admin/content-packs?is_active=true` → 200 OK (with auth) or 403 Forbidden (without proper role)
- `GET /api/v1/admin/content-packs/test` → 200 OK (no auth required)

### Route Path Structure

```
Router prefix: /api/v1
Route path: /admin/content-packs
Full path: /api/v1/admin/content-packs
```

### Authentication Requirements

The `/admin/content-packs` endpoint requires:
- Valid Bearer token in Authorization header
- User must have one of these roles:
  - `org_admin`
  - `institution_admin`
  - `super_admin`

### Quick Test Commands

```bash
# Test endpoint (no auth)
curl https://1nebackend-production.up.railway.app/api/v1/admin/content-packs/test

# List routes (if /api/routes endpoint is available)
curl https://1nebackend-production.up.railway.app/api/routes

# Check health
curl https://1nebackend-production.up.railway.app/health
```

### Next Steps

1. **Restart Railway backend** - This is the most likely fix
2. **Check Railway logs** - Look for errors during startup
3. **Verify authentication** - Ensure you're sending a valid token
4. **Check user role** - Ensure your user has the required role
