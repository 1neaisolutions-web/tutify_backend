# Fix Backend Connection - Kill All Instances and Start Clean
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "FIXING BACKEND CONNECTION" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan

# Step 1: Kill all backend processes
Write-Host "1️⃣  Killing all backend processes..." -ForegroundColor Yellow
$processes = Get-Process | Where-Object {$_.ProcessName -like "*python*" -or $_.ProcessName -like "*uvicorn*"}
if ($processes) {
    Write-Host "Found $($processes.Count) processes to kill" -ForegroundColor White
    $processes | ForEach-Object {
        try {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  ✓ Killed process $($_.Id) ($($_.ProcessName))" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ Could not kill process $($_.Id): $_" -ForegroundColor Red
        }
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host "  No processes found" -ForegroundColor Gray
}

# Step 2: Verify port is free
Write-Host "`n2️⃣  Checking port 8000..." -ForegroundColor Yellow
Start-Sleep -Seconds 1
$portCheck = netstat -ano | findstr :8000
if ($portCheck) {
    Write-Host "  ⚠️  Port 8000 still in use:" -ForegroundColor Red
    Write-Host $portCheck -ForegroundColor Red
    Write-Host "`n  Waiting 3 seconds and trying again..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    $portCheck2 = netstat -ano | findstr :8000
    if ($portCheck2) {
        Write-Host "  ❌ Port still in use. Please manually kill processes:" -ForegroundColor Red
        Write-Host $portCheck2 -ForegroundColor Red
        Write-Host "`n  Run: taskkill /F /IM python.exe" -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "  ✅ Port 8000 is free" -ForegroundColor Green

# Step 3: Change to backend directory
Write-Host "`n3️⃣  Navigating to backend directory..." -ForegroundColor Yellow
Set-Location "D:\1ne\1ne_backend"
Write-Host "  ✅ In directory: $(Get-Location)" -ForegroundColor Green

# Step 4: Start ONE clean backend instance
Write-Host "`n4️⃣  Starting clean backend instance..." -ForegroundColor Yellow
Write-Host "  📍 URL: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  📚 Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "  🏥 Health: http://127.0.0.1:8000/health" -ForegroundColor Cyan
Write-Host "`n  ⏳ Starting in 2 seconds...`n" -ForegroundColor Yellow
Start-Sleep -Seconds 2

# Start the server
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
