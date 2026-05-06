# Test Content Ingestion Endpoints Locally

## Quick Start

1. **Start the backend:**
   ```powershell
   cd 1ne_backend
   .\start_server.ps1
   ```
   Backend should be running on `http://127.0.0.1:8000`

2. **Configure frontend to use localhost:**
   Create or update `1ne-frontend/.env`:
   ```
   VITE_USE_LOCAL=true
   ```
   Or set:
   ```
   VITE_API_BASE_URL=http://127.0.0.1:8000
   ```

3. **Run the test script:**
   ```powershell
   cd 1ne_backend
   python test_content_endpoints_local.py
   ```

## Expected Results

### ✅ Success Indicators:
- Health check returns 200 OK
- Test endpoint (`/api/v1/admin/content-packs/test`) returns 200 OK
- All other endpoints return **401 Unauthorized** or **403 Forbidden** (NOT 404)
- Routes endpoint shows all content ingestion routes

### ❌ Failure Indicators:
- Any endpoint returns **404 Not Found** → Routes not registered
- Connection errors → Backend not running
- Import errors in backend logs → Check dependencies

## Manual Testing

### 1. Test Endpoint (No Auth)
```bash
curl http://127.0.0.1:8000/api/v1/admin/content-packs/test
```
Expected: `{"message": "Content packs route is working", "status": "ok", ...}`

### 2. List All Routes
```bash
curl http://127.0.0.1:8000/api/routes
```
Expected: JSON with all routes including `/api/v1/admin/content-packs`

### 3. FastAPI Docs
Visit: http://127.0.0.1:8000/docs
- Look for "content-ingestion" tag
- Should see all endpoints listed

### 4. Test with Auth (if you have token)
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://127.0.0.1:8000/api/v1/admin/content-packs?is_active=true
```

## Troubleshooting

### Backend Not Starting
- Check if port 8000 is in use
- Check database connection
- Check Python virtual environment is activated
- Check all dependencies are installed

### Routes Not Found (404)
- Check backend logs for import errors
- Verify `app/api/v1/__init__.py` imports content_ingestion routes
- Verify `app/main.py` includes v1_router
- Restart backend server

### Frontend Still Calling Railway
- Check `1ne-frontend/.env` has `VITE_USE_LOCAL=true`
- Restart frontend dev server after changing .env
- Check browser console for API calls
