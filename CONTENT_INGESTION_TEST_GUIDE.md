# Content Ingestion Endpoints Test Guide

## Overview

This guide explains how to test the newly added Content Ingestion API endpoints to ensure they work as expected.

## Prerequisites

1. **Backend server must be running**
   ```powershell
   cd 1ne_backend
   .\venv\Scripts\activate
   python -m uvicorn app.main:app --reload
   ```

2. **Install dependencies** (if not already installed)
   ```powershell
   pip install requests
   # OR
   pip install -r requirements.txt
   ```

3. **Database must be migrated**
   ```powershell
   alembic upgrade head
   ```

## Running the Tests

### Option 1: Using the Test Script (Recommended)

```powershell
cd 1ne_backend
python test_content_ingestion_endpoints.py
```

The script will:
- ✅ Check if the server is running
- ✅ Test the test endpoint (no auth required)
- ✅ Attempt to authenticate (requires admin user)
- ✅ Test all content ingestion endpoints
- ✅ Provide a detailed summary

### Option 2: Manual Testing via Browser/Postman

1. **Test Endpoint (No Auth Required)**
   ```
   GET http://localhost:8000/api/v1/admin/content-packs/test
   ```
   Expected: `{"message": "Content packs route is working", "status": "ok", "path": "/api/v1/admin/content-packs"}`

2. **List Content Packs** (Requires Auth)
   ```
   GET http://localhost:8000/api/v1/admin/content-packs?is_active=true
   Headers: Authorization: Bearer <your_token>
   ```
   Expected: Array of content packs

3. **Create Content Pack** (Requires Auth)
   ```
   POST http://localhost:8000/api/v1/admin/content-packs
   Headers: 
     Authorization: Bearer <your_token>
     Content-Type: application/json
   Body:
   {
     "name": "Test Pack",
     "description": "Test description",
     "subject": "Mathematics",
     "grade": "Grade 10"
   }
   ```
   Expected: Created content pack with ID

## Endpoints Being Tested

### Content Pack Endpoints

1. **GET /api/v1/admin/content-packs/test**
   - No authentication required
   - Tests route registration

2. **GET /api/v1/admin/content-packs**
   - Requires: `org_admin`, `institution_admin`, or `super_admin` role
   - Lists all content packs for the user's tenant
   - Query params: `skip`, `limit`, `is_active`

3. **POST /api/v1/admin/content-packs**
   - Requires: `org_admin`, `institution_admin`, or `super_admin` role
   - Creates a new content pack

4. **GET /api/v1/admin/content-packs/{pack_id}**
   - Requires: `org_admin`, `institution_admin`, or `super_admin` role
   - Gets details of a specific content pack

### Document Endpoints

5. **GET /api/v1/admin/documents**
   - Requires: `org_admin`, `institution_admin`, or `super_admin` role
   - Lists all documents for the user's tenant
   - Query params: `pack_id`, `status_filter`, `skip`, `limit`

### Worksheet Endpoints

6. **POST /api/v1/worksheets/generate**
   - Requires: Any authenticated user
   - Generates a worksheet using RAG
   - Body: `pack_id`, `topic_text`, `grade`, `subject`, `num_questions`, etc.

7. **GET /api/v1/worksheets/{worksheet_id}**
   - Requires: Any authenticated user
   - Gets a cached worksheet by ID

## Expected Test Results

### ✅ Success Scenarios

- **Test Endpoint**: Should return 200 with test message
- **List Content Packs**: Should return 200 with array (may be empty)
- **Create Content Pack**: Should return 201 with created pack
- **Get Content Pack**: Should return 200 with pack details
- **List Documents**: Should return 200 with array (may be empty)

### ⚠️ Expected Failures (If User Lacks Role)

- **403 Forbidden**: User doesn't have required role (`org_admin`, `institution_admin`, or `super_admin`)
- **401 Unauthorized**: Invalid or missing authentication token

## Troubleshooting

### Issue: "Server is not running"
**Solution**: Start the backend server first
```powershell
python -m uvicorn app.main:app --reload
```

### Issue: "ModuleNotFoundError: No module named 'requests'"
**Solution**: Install requests
```powershell
pip install requests
```

### Issue: "403 Forbidden" on admin endpoints
**Solution**: Ensure your test user has one of these roles:
- `org_admin`
- `institution_admin`
- `super_admin`

### Issue: "404 Not Found" on endpoints
**Solution**: 
1. Verify the server has been restarted after code changes
2. Check that routes are registered in `/docs` endpoint
3. Verify the route path is correct

## Verification Checklist

- [ ] Server is running and accessible
- [ ] Test endpoint returns 200
- [ ] Authentication works (can get token)
- [ ] List content packs returns 200 (or 403 if no role)
- [ ] Create content pack returns 201 (or 403 if no role)
- [ ] Get content pack returns 200 (or 404 if not found)
- [ ] List documents returns 200 (or 403 if no role)
- [ ] All endpoints return appropriate status codes

## Next Steps

After verifying endpoints work:
1. Test document upload functionality
2. Test document processing status streaming
3. Test QA validation endpoints
4. Test worksheet generation with real content packs
5. Test publish workflow

## Notes

- The test script uses default credentials (`admin@test.com` / `Test123!@#`)
- You may need to create a test user with appropriate roles
- Some endpoints may return empty arrays if no data exists (this is expected)
- Worksheet generation requires a valid `pack_id` and may take longer due to LLM calls
