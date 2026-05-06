# Comprehensive Check and Fix Script
# This script checks for issues and fixes them automatically
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Comprehensive Check and Fix" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$backendDir = "C:\Users\rttsg\OneDrive\Desktop\1ne\1ne_backend"
Set-Location $backendDir

$issuesFound = @()
$fixesApplied = @()

# Check 1: .env file exists
Write-Host "1. Checking .env file..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "   ✅ .env file exists" -ForegroundColor Green
} else {
    Write-Host "   ❌ .env file NOT found!" -ForegroundColor Red
    $issuesFound += ".env file missing"
    if (Test-Path ".env.example") {
        Write-Host "   📋 Copying .env.example to .env..." -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
        Write-Host "   ✅ Created .env from .env.example" -ForegroundColor Green
        Write-Host "   ⚠️  Please update DATABASE_URL in .env file!" -ForegroundColor Yellow
        $fixesApplied += "Created .env file"
    }
}

# Check 2: Virtual environment
Write-Host "`n2. Checking virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\python.exe") {
    Write-Host "   ✅ Virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "   ❌ Virtual environment NOT found!" -ForegroundColor Red
    $issuesFound += "Virtual environment missing"
}

# Check 3: Database connection
Write-Host "`n3. Testing database connection..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\python.exe") {
    $dbTest = .\venv\Scripts\python.exe -c "from app.core.config import settings; from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1')); print('OK'); db.close()" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ Database connection successful" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Database connection failed" -ForegroundColor Red
        Write-Host "   Error: $dbTest" -ForegroundColor Red
        $issuesFound += "Database connection failed"
    }
} else {
    Write-Host "   ⚠️  Skipping (venv not found)" -ForegroundColor Yellow
}

# Check 4: Check if content_packs table exists
Write-Host "`n4. Checking if content_packs table exists..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\python.exe") {
    $tableCheck = .\venv\Scripts\python.exe -c "from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1 FROM content_packs LIMIT 1')); print('EXISTS'); db.close()" 2>&1
    if ($LASTEXITCODE -eq 0 -and $tableCheck -match "EXISTS") {
        Write-Host "   ✅ content_packs table exists" -ForegroundColor Green
    } else {
        Write-Host "   ❌ content_packs table does NOT exist!" -ForegroundColor Red
        Write-Host "   This is causing the network errors!" -ForegroundColor Red
        $issuesFound += "content_packs table missing"
        
        # Auto-fix: Run migration
        Write-Host "`n   🔧 AUTO-FIX: Running database migration..." -ForegroundColor Yellow
        $migrationOutput = .\venv\Scripts\python.exe -m alembic upgrade head 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ Migration completed successfully!" -ForegroundColor Green
            $fixesApplied += "Ran database migration - created content_packs table"
            
            # Verify fix
            $verify = .\venv\Scripts\python.exe -c "from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1 FROM content_packs LIMIT 1')); print('OK'); db.close()" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   ✅ Verified: content_packs table now exists!" -ForegroundColor Green
            }
        } else {
            Write-Host "   ❌ Migration failed!" -ForegroundColor Red
            Write-Host "   Output: $migrationOutput" -ForegroundColor Red
            $issuesFound += "Migration failed"
        }
    }
} else {
    Write-Host "   ⚠️  Skipping (venv not found)" -ForegroundColor Yellow
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

if ($issuesFound.Count -eq 0) {
    Write-Host "✅ No issues found! Everything looks good." -ForegroundColor Green
} else {
    Write-Host "⚠️  Issues found:" -ForegroundColor Yellow
    foreach ($issue in $issuesFound) {
        Write-Host "   - $issue" -ForegroundColor Red
    }
}

if ($fixesApplied.Count -gt 0) {
    Write-Host "`n✅ Fixes applied:" -ForegroundColor Green
    foreach ($fix in $fixesApplied) {
        Write-Host "   - $fix" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. If migration ran, restart your backend server" -ForegroundColor White
Write-Host "2. The network errors should now be fixed" -ForegroundColor White
Write-Host "3. If issues persist, check DATABASE_URL in .env" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
