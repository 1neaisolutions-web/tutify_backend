# Start Backend Server - Simple and Direct
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Backend Server" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to backend (script lives in 1ne_backend — portable for any clone path)
$backendDir = $PSScriptRoot
Set-Location $backendDir

# Check venv
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    exit 1
}

# Check dependencies
Write-Host "Checking dependencies..." -ForegroundColor Yellow
$check = .\venv\Scripts\python.exe -c "import fastapi, uvicorn; print('OK')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Dependencies missing!" -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies OK" -ForegroundColor Green
Write-Host ""

# Clear port if needed (matches 1ne-frontend .env: VITE_API_BASE_URL on port 8000)
$existing = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Port 8000 is in use. Clearing..." -ForegroundColor Yellow
    $existing | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# Start server
Write-Host "Starting server on http://127.0.0.1:8000..." -ForegroundColor Green
Write-Host "Server will start in this window." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""
Write-Host "Waiting for startup..." -ForegroundColor Yellow
Write-Host ""

.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
