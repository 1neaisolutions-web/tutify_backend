# Check Environment Variables
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Checking Environment Configuration" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$backendDir = "C:\Users\rttsg\OneDrive\Desktop\1ne\1ne_backend"
Set-Location $backendDir

# Check if .env exists
if (Test-Path ".env") {
    Write-Host "✅ .env file exists" -ForegroundColor Green
} else {
    Write-Host "❌ .env file NOT found!" -ForegroundColor Red
    Write-Host "   Create it from .env.example" -ForegroundColor Yellow
    exit 1
}

# Check critical variables
Write-Host "`nChecking critical variables..." -ForegroundColor Yellow

# Load .env file (simple check)
$envContent = Get-Content .env -Raw

$checks = @{
    "DATABASE_URL" = $false
    "SECRET_KEY" = $false
}

foreach ($key in $checks.Keys) {
    if ($envContent -match "$key=") {
        $value = ($envContent -split "$key=")[1] -split "`n" | Select-Object -First 1
        if ($value -and $value.Trim() -ne "" -and $value.Trim() -notmatch "^(your-|postgresql://user:password)") {
            Write-Host "✅ $key is set" -ForegroundColor Green
            $checks[$key] = $true
        } else {
            Write-Host "⚠️  $key is using default/placeholder value" -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ $key is NOT set" -ForegroundColor Red
    }
}

# Check database connection
Write-Host "`nTesting database connection..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\python.exe") {
    $result = .\venv\Scripts\python.exe -c "from app.core.config import settings; from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1')); print('✅ Database connected'); db.close()" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host $result -ForegroundColor Green
    } else {
        Write-Host "❌ Database connection failed" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
    }
} else {
    Write-Host "⚠️  Virtual environment not found, skipping DB test" -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Check complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
