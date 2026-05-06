# Local Endpoint Testing - Complete Guide

## ✅ Code Status: ALL ROUTES ARE CORRECTLY CONFIGURED

All content ingestion endpoints are properly:
- ✅ Defined in `app/domains/content_ingestion/routes.py`
- ✅ Registered in `app/api/v1/__init__.py`
- ✅ Included in `app/main.py`
- ✅ No syntax errors or import issues

## 🚀 Quick Start: Test Locally

### 1. Start Backend
```powershell
cd 1ne_backend
.\start_server.ps1
```
Wait for: `Application startup complete`

### 2. Verify Routes (Optional but Recommended)
```powershell
cd 1ne_backend
python verify_routes.py
```
Should show: ✅ Routes are properly registered

### 3. Test Endpoints
```powershell
cd 1ne_backend
python test_content_endpoints_local.py
```

### 4. Check FastAPI Docs
Open browser: http://127.0.0.1:8000/docs
- Look for **"content-ingestion"** tag
- Should see all endpoints listed

## 📋 All Content Ingestion Endpoints

### Content Packs
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/admin/content-packs/test` | ❌ No | Test route registration |
| GET | `/api/v1/admin/content-packs` | ✅ Yes | List all packs |
| POST | `/api/v1/admin/content-packs` | ✅ Yes | Create new pack |
| GET | `/api/v1/admin/content-packs/{pack_id}` | ✅ Yes | Get single pack |

### Documents
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/admin/documents` | ✅ Yes | List all documents |
| POST | `/api/v1/admin/documents/upload-stream` | ✅ Yes | Upload document (streaming) |
| GET | `/api/v1/admin/documents/{document_id}` | ✅ Yes | Get single document |
| POST | `/api/v1/admin/documents/{document_id}/retry` | ✅ Yes | Retry processing |
| GET | `/api/v1/admin/documents/{document_id}/status/stream` | ✅ Yes | Status stream (SSE) |
| POST | `/api/v1/admin/documents/{document_id}/qa/run` | ✅ Yes | Run QA validation |
| POST | `/api/v1/admin/documents/{document_id}/publish` | ✅ Yes | Publish document |

### Worksheets
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/worksheets/generate` | ✅ Yes | Generate worksheet |
| GET | `/api/v1/worksheets/{worksheet_id}` | ✅ Yes | Get worksheet |

## 🧪 Manual Testing Commands

### Test 1: No Auth Endpoint
```bash
curl http://127.0.0.1:8000/api/v1/admin/content-packs/test
```
**Expected:** `{"message": "Content packs route is working", "status": "ok", ...}`

### Test 2: List All Routes
```bash
curl http://127.0.0.1:8000/api/routes
```
**Expected:** JSON with all routes including content ingestion endpoints

### Test 3: Health Check
```bash
curl http://127.0.0.1:8000/health
```
**Expected:** `{"status": "ok", "database": "connected"}`

### Test 4: With Authentication
```bash
# First, get a token from login endpoint
TOKEN="your_token_here"

# Then test content packs endpoint
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/admin/content-packs?is_active=true
```

## 🔍 Expected Responses

### ✅ Success (Route Exists)
- **200 OK** - Request successful (with valid auth)
- **201 Created** - Resource created (POST requests)
- **401 Unauthorized** - No auth token provided (route exists!)
- **403 Forbidden** - Auth token invalid or wrong role (route exists!)

### ❌ Failure (Route NOT Found)
- **404 Not Found** - Route doesn't exist (check backend logs)

## 🐛 Troubleshooting

### Problem: All endpoints return 404

**Solution:**
1. Check backend is running: `curl http://127.0.0.1:8000/health`
2. Check backend logs for errors
3. Run `python verify_routes.py` to verify registration
4. Restart backend server

### Problem: Backend won't start

**Check:**
- Port 8000 is free
- Database is running and accessible
- Virtual environment is activated
- All dependencies installed: `pip install -r requirements.txt`

### Problem: Import errors in logs

**Check:**
- All dependencies installed
- Python path is correct
- No circular imports
- Check `app/api/v1/__init__.py` for import errors

### Problem: Frontend still calls Railway

**Solution:**
1. Create `1ne-frontend/.env` file:
   ```
   VITE_USE_LOCAL=true
   ```
2. Restart frontend dev server
3. Check browser console for API URL

## 📊 Verification Checklist

- [ ] Backend starts without errors
- [ ] Health check returns 200 OK
- [ ] Test endpoint (`/api/v1/admin/content-packs/test`) returns 200 OK
- [ ] FastAPI docs show "content-ingestion" tag
- [ ] All endpoints return 401/403 (not 404) without auth
- [ ] Routes endpoint shows content ingestion routes
- [ ] Frontend configured to use localhost
- [ ] Frontend can call endpoints (with auth)

## 🎯 Next Steps After Local Testing

1. **Test with authentication:**
   - Login to get token
   - Test all endpoints with token
   - Verify CRUD operations work

2. **Test frontend integration:**
   - Configure frontend for localhost
   - Test UI flows
   - Verify real-time updates work

3. **Deploy to Railway:**
   - Push code to repository
   - Railway auto-deploys
   - Test on production URL

---

**Remember:** If endpoints return 401/403 (not 404), the routes ARE registered correctly! You just need authentication.
