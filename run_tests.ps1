# Test script with timeout protection
Write-Host "Running API Endpoint Tests..." -ForegroundColor Green
Write-Host "Make sure the server is running first!`n" -ForegroundColor Yellow

# Check if server is running
$checkServer = @'
import requests
try:
    r = requests.get("http://localhost:8000/health", timeout=3)
    if r.status_code == 200:
        exit(0)
    else:
        exit(1)
except:
    exit(1)
'@

$result = $checkServer | .\venv\Scripts\python.exe - 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Server is not running!" -ForegroundColor Red
    Write-Host "Please start the server first with: .\start_server.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "Server is running. Starting tests...`n" -ForegroundColor Green

# Run test script with timeout
$job = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    .\venv\Scripts\python.exe test_api_endpoints.py
}

# Wait with timeout
$timeout = 120  # 2 minutes
$completed = Wait-Job $job -Timeout $timeout

if (-not $completed) {
    Write-Host "`nERROR: Tests timed out after $timeout seconds" -ForegroundColor Red
    Stop-Job $job
    Remove-Job $job
    exit 1
}

# Get results
$output = Receive-Job $job
Remove-Job $job

Write-Host $output

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nAll tests completed!" -ForegroundColor Green
} else {
    Write-Host "`nSome tests failed!" -ForegroundColor Red
}

