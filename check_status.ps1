# Quick status check script
Write-Host "=== 1ne.ai Backend Status Check ===" -ForegroundColor Cyan
Write-Host ""

# Check virtual environment
Write-Host "1. Virtual Environment:" -ForegroundColor Yellow
if (Test-Path "venv\Scripts\python.exe") {
    Write-Host "   ✓ Virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "   ✗ Virtual environment NOT found" -ForegroundColor Red
    Write-Host "     Run: python -m venv venv" -ForegroundColor Yellow
}

# Check dependencies
Write-Host ""
Write-Host "2. Dependencies:" -ForegroundColor Yellow
$depCheck = .\venv\Scripts\python.exe -c "import fastapi; print('OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✓ Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "   ✗ Dependencies NOT installed" -ForegroundColor Red
    Write-Host "     Run: .\venv\Scripts\activate; pip install -r requirements.txt" -ForegroundColor Yellow
}

# Check server
Write-Host ""
Write-Host "3. Server Status:" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✓ Server is running on http://localhost:8000" -ForegroundColor Green
    } else {
        Write-Host "   ✗ Server returned error status" -ForegroundColor Red
    }
} catch {
    Write-Host "   ✗ Server is NOT running" -ForegroundColor Red
    Write-Host "     Run: .\start_server.ps1" -ForegroundColor Yellow
}

Write-Host ""
