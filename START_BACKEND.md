# Start Backend Server - Quick Guide

## Quick Start

```powershell
cd 1ne_backend
.\start_backend_now.ps1
```

**Local frontend (`1ne-frontend`)** often uses `VITE_API_BASE_URL=http://127.0.0.1:8000` in `.env`. Run the API on **port 8000** so login and API calls work without changing the frontend. Example:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or use `.\start_backend_now.ps1` (uses port 8000 when your venv is at `venv\`).

## What to Expect

1. **Server starts on:** `http://127.0.0.1:8000` (use **8001** only if your frontend `.env` points at that port instead)
2. **You should see:** `Application startup complete`
3. **FastAPI docs:** `http://127.0.0.1:8000/docs`

## Verify Backend is Running

### Option 1: Check Health Endpoint
```powershell
curl http://127.0.0.1:8000/health
```
Expected: `{"status": "ok", "database": "connected"}`

### Option 2: Open in Browser
Visit: `http://127.0.0.1:8000/docs`

### Option 3: Test Content Packs Endpoint
```powershell
curl http://127.0.0.1:8000/api/v1/admin/content-packs/test
```
Expected: `{"message": "Content packs route is working", ...}`

## Troubleshooting

### Port 8000 Already in Use

**Error:** `Address already in use` or `Port 8000 is already in use`

**Solution:**
1. Find process using port 8000:
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
   ```
2. Kill the process:
   ```powershell
   Stop-Process -Id <PID> -Force
   ```
3. Or use a different port:
   ```powershell
   .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
   ```
   Then update frontend `.env` to use port 8001.

### Database Connection Error

**Error:** `Database connection failed`

**Solution:**
1. Check database is running
2. Verify `DATABASE_URL` in backend `.env` is correct
3. Check network connectivity to database

### Virtual Environment Not Found

**Error:** `Virtual environment not found`

**Solution:**
```powershell
cd 1ne_backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Dependencies Not Installed

**Error:** `ModuleNotFoundError`

**Solution:**
```powershell
cd 1ne_backend
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Manual Start (Alternative)

If the script doesn't work:

```powershell
cd 1ne_backend
.\venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Check if Backend is Running

```powershell
# Test health endpoint
curl http://127.0.0.1:8000/health

# Or use PowerShell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing
```
