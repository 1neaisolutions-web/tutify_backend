# Stop any process on port 8000, then start backend with venv + uvicorn
$ErrorActionPreference = "SilentlyContinue"
Set-Location $PSScriptRoot

Write-Host "Stopping any process on port 8000..." -ForegroundColor Yellow
# Method 1: Get-NetTCPConnection
$connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
$pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($p in $pids) {
    if ($p -gt 0) {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        Write-Host "  Stopped PID $p" -ForegroundColor Gray
    }
}
# Method 2: netstat + taskkill (catches PIDs that may be child processes)
$lines = netstat -ano | Select-String "127.0.0.1:8000\s+0.0.0.0:0\s+LISTENING"
foreach ($line in $lines) {
    if ($line -match "\s+(\d+)\s*$") {
        $p = [int]$Matches[1]
        if ($p -gt 0) {
            & taskkill /F /PID $p 2>$null
            Write-Host "  taskkill PID $p" -ForegroundColor Gray
        }
    }
}
Start-Sleep -Seconds 4
Write-Host "Port 8000 cleared. Starting server..." -ForegroundColor Green

Write-Host "Starting backend with virtual environment (uvicorn)..." -ForegroundColor Green
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "ERROR: venv not found. Run: python -m venv venv" -ForegroundColor Red
    exit 1
}
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
