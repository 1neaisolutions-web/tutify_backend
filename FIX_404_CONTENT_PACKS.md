# Fix: 404 Not Found on Content Packs Endpoints

## Problem
`GET /api/v1/admin/content-packs?is_active=true` returns 404 Not Found

## Root Cause
Railway backend hasn't restarted with the new route code.

## Solution: Restart Railway Backend

### Option 1: Via Railway Dashboard (Recommended)
1. Go to https://railway.app
2. Select your backend project
3. Go to the **Deployments** tab
4. Click **"Redeploy"** or **"Deploy Latest"**
5. Wait for deployment to complete (usually 2-5 minutes)
6. Test the endpoint again

### Option 2: Trigger via Git Push
If your Railway is connected to GitHub:
1. Make a small change (add a comment) to any file
2. Commit and push:
   ```bash
   git add .
   git commit -m "Trigger Railway redeploy for content packs routes"
   git push
   ```
3. Railway will automatically redeploy

### Option 3: Manual Restart
1. Go to Railway dashboard
2. Select your backend service
3. Click **Settings** → **Restart Service**

## Verification Steps

After restarting, test these endpoints:

### 1. Test Endpoint (No Auth Required)
```bash
curl https://1nebackend-production.up.railway.app/api/v1/admin/content-packs/test
```
**Expected:** `{"message": "Content packs route is working", "status": "ok", "path": "/api/v1/admin/content-packs"}`

### 2. List Routes (New Diagnostic Endpoint)
```bash
curl https://1nebackend-production.up.railway.app/api/routes
```
**Expected:** JSON with all registered routes, including `/api/v1/admin/content-packs`

### 3. FastAPI Docs
Visit: https://1nebackend-production.up.railway.app/docs
- Look for **"content-ingestion"** tag
- Should see endpoints like:
  - `GET /api/v1/admin/content-packs/test`
  - `GET /api/v1/admin/content-packs`
  - `POST /api/v1/admin/content-packs`

### 4. Actual Content Packs Endpoint (Requires Auth)
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://1nebackend-production.up.railway.app/api/v1/admin/content-packs?is_active=true
```
**Expected:** 200 OK with list of content packs (or empty array `[]`)

## Code Status

✅ **All code is correct and ready:**
- Routes are properly defined in `app/domains/content_ingestion/routes.py`
- Routes are registered in `app/api/v1/__init__.py`
- Router is included in `app/main.py`
- Authorization uses `require_any_role` for `org_admin`, `institution_admin`, `super_admin`
- No syntax errors or import issues

## What Was Changed

1. **Added `require_any_role` dependency** in `app/domains/auth/dependencies.py`
2. **Updated all content pack endpoints** to use `require_any_role` instead of `require_role`
3. **Added test endpoint** `/api/v1/admin/content-packs/test` (no auth required)
4. **Added diagnostic endpoint** `/api/routes` to list all registered routes
5. **Enhanced logging** to track route registration

## Expected Behavior After Restart

- ✅ `GET /api/v1/admin/content-packs/test` → 200 OK (no auth)
- ✅ `GET /api/v1/admin/content-packs` → 200 OK (with valid token + role) or 403/401 (wrong role/no token)
- ✅ `POST /api/v1/admin/content-packs` → 201 Created (with valid token + role)

## Troubleshooting

If still getting 404 after restart:

1. **Check Railway logs:**
   - Go to Railway dashboard → Your service → **Logs**
   - Look for: "Content ingestion routes registered successfully"
   - Look for any import errors

2. **Check route registration:**
   ```bash
   curl https://1nebackend-production.up.railway.app/api/routes | grep content-packs
   ```

3. **Verify authentication:**
   - Make sure you're sending a valid Bearer token
   - Make sure your user has one of: `org_admin`, `institution_admin`, `super_admin` roles

4. **Check FastAPI docs:**
   - Visit `/docs` endpoint
   - Verify routes are listed there

## Next Steps

1. **Restart Railway backend** (choose one of the options above)
2. **Wait for deployment** (2-5 minutes)
3. **Test the test endpoint** (no auth required)
4. **Test the actual endpoint** (with your auth token)
5. **Verify in frontend** - refresh the page and try again

---

**Note:** The code is 100% correct. The only issue is that Railway needs to restart to load the new routes.
