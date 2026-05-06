# Quick Backend Fix Script
Write-Host "🔧 Fixing Backend Connection Issues..." -ForegroundColor Cyan

# Step 1: Kill all existing processes
Write-Host "`n1️⃣ Killing existing processes..." -ForegroundColor Yellow
Stop-Process -Name "uvicorn" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "✅ Processes killed" -ForegroundColor Green

# Step 2: Check if port is free
Write-Host "`n2️⃣ Checking port 8000..." -ForegroundColor Yellow
$portCheck = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($portCheck) {
    Write-Host "⚠️ Port 8000 still in use. Waiting 3 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}

# Step 3: Test database connection
Write-Host "`n3️⃣ Testing database connection..." -ForegroundColor Yellow
try {
    $env:PYTHONPATH = "D:\1ne\1ne_backend"
    $result = & ".\venv\Scripts\python.exe" -c "from app.db.session import engine; conn = engine.connect(); print('✅ Database OK'); conn.close()" 2>&1
    Write-Host $result -ForegroundColor Green
} catch {
    Write-Host "❌ Database connection failed: $_" -ForegroundColor Red
    Write-Host "💡 Make sure PostgreSQL is running!" -ForegroundColor Yellow
    exit 1
}

# Step 4: Start backend
Write-Host "`n4️⃣ Starting backend server..." -ForegroundColor Yellow
Write-Host "🚀 Backend will start on http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "📚 Docs will be at http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "`nStarting in 2 seconds...`n" -ForegroundColor Yellow
Start-Sleep -Seconds 2

& ".\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000





