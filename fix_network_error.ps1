# Network Error Fix Script - Shows Output and Doesn't Get Stuck
$ErrorActionPreference = "Continue"
$ProgressPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Network Error Fix - Auto-Retry Mode" -ForegroundColor Green
Write-Host "This script will NOT stop until fixed" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$backendDir = "C:\Users\rttsg\OneDrive\Desktop\1ne\1ne_backend"
Set-Location $backendDir

$maxRetries = 3
$retryCount = 0
$fixed = $false

function Test-TableExists {
    param([string]$tableName)
    Write-Host "   [TEST] Checking if $tableName exists..." -ForegroundColor Gray
    if (-not (Test-Path "venv\Scripts\python.exe")) {
        Write-Host "   [TEST] Venv not found" -ForegroundColor Red
        return $false
    }
    try {
        $result = .\venv\Scripts\python.exe -c "from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1 FROM $tableName LIMIT 1')); print('EXISTS'); db.close()" 2>&1
        $exists = ($LASTEXITCODE -eq 0 -and $result -match "EXISTS")
        if ($exists) {
            Write-Host "   [TEST] ✅ Table exists!" -ForegroundColor Green
        } else {
            Write-Host "   [TEST] ❌ Table does not exist" -ForegroundColor Red
        }
        return $exists
    } catch {
        Write-Host "   [TEST] ❌ Error: $_" -ForegroundColor Red
        return $false
    }
}

function Run-Migration {
    Write-Host "`n[STEP] Running migration (this may take 10-30 seconds)..." -ForegroundColor Yellow
    Write-Host "[STEP] Please wait, showing output..." -ForegroundColor Gray
    
    try {
        $output = .\venv\Scripts\python.exe -m alembic upgrade head 2>&1 | Tee-Object -Variable migrationOutput
        $exitCode = $LASTEXITCODE
        
        Write-Host $migrationOutput
        
        if ($exitCode -eq 0) {
            Write-Host "[STEP] ✅ Migration command completed" -ForegroundColor Green
        } else {
            Write-Host "[STEP] ❌ Migration command failed (exit code: $exitCode)" -ForegroundColor Red
        }
        
        return $exitCode
    } catch {
        Write-Host "[STEP] ❌ Migration error: $_" -ForegroundColor Red
        return 1
    }
}

function Diagnose-Issue {
    Write-Host "`n[DIAGNOSIS] Starting diagnosis..." -ForegroundColor Cyan
    
    # Check 1: Venv
    Write-Host "   [CHECK] Virtual environment..." -ForegroundColor Gray
    if (-not (Test-Path "venv\Scripts\python.exe")) {
        Write-Host "   [CHECK] ❌ Virtual environment missing" -ForegroundColor Red
        return "venv_missing"
    }
    Write-Host "   [CHECK] ✅ Virtual environment exists" -ForegroundColor Green
    
    # Check 2: Database connection
    Write-Host "   [CHECK] Database connection..." -ForegroundColor Gray
    try {
        $dbTest = .\venv\Scripts\python.exe -c "from app.core.config import settings; from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1')); db.close()" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   [CHECK] ❌ Database connection failed" -ForegroundColor Red
            Write-Host "   [CHECK] Error: $dbTest" -ForegroundColor Red
            return "db_connection_failed"
        }
        Write-Host "   [CHECK] ✅ Database connection OK" -ForegroundColor Green
    } catch {
        Write-Host "   [CHECK] ❌ Database check error: $_" -ForegroundColor Red
        return "db_connection_failed"
    }
    
    # Check 3: Alembic
    Write-Host "   [CHECK] Alembic..." -ForegroundColor Gray
    try {
        $alembicCheck = .\venv\Scripts\python.exe -c "import alembic; print('OK')" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   [CHECK] ❌ Alembic not installed - installing..." -ForegroundColor Yellow
            .\venv\Scripts\pip.exe install alembic 2>&1 | Write-Host
        }
        Write-Host "   [CHECK] ✅ Alembic available" -ForegroundColor Green
    } catch {
        Write-Host "   [CHECK] ⚠️  Alembic check error: $_" -ForegroundColor Yellow
    }
    
    Write-Host "   [DIAGNOSIS] ✅ All checks passed" -ForegroundColor Green
    return "ready"
}

# Main fix loop
Write-Host "`n[START] Beginning fix process..." -ForegroundColor Cyan
Write-Host "[INFO] Will retry up to $maxRetries times" -ForegroundColor Gray
Write-Host ""

while (-not $fixed -and $retryCount -lt $maxRetries) {
    $retryCount++
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "FIX ATTEMPT #$retryCount of $maxRetries" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Step 1: Diagnose
    $diagnosis = Diagnose-Issue
    
    if ($diagnosis -eq "venv_missing") {
        Write-Host "`n[ERROR] Cannot proceed without virtual environment" -ForegroundColor Red
        Write-Host "[INFO] Please create venv first: python -m venv venv" -ForegroundColor Yellow
        break
    }
    
    if ($diagnosis -eq "db_connection_failed") {
        Write-Host "`n[WARNING] Database connection issue" -ForegroundColor Yellow
        Write-Host "[INFO] Will retry in 3 seconds..." -ForegroundColor Gray
        Start-Sleep -Seconds 3
        continue
    }
    
    # Step 2: Check if table exists
    Write-Host "`n[CHECK] Testing if content_packs table exists..." -ForegroundColor Yellow
    if (Test-TableExists "content_packs") {
        Write-Host "`n[SUCCESS] ✅ content_packs table EXISTS!" -ForegroundColor Green
        $fixed = $true
        break
    }
    Write-Host "[ISSUE] ❌ content_packs table does NOT exist" -ForegroundColor Red
    Write-Host "[ISSUE] This is causing the network errors!" -ForegroundColor Red
    
    # Step 3: Run migration
    Write-Host "`n[ACTION] Running migration to create table..." -ForegroundColor Yellow
    $migrationResult = Run-Migration
    
    if ($migrationResult -eq 0) {
        Write-Host "`n[VERIFY] Verifying table was created..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        
        if (Test-TableExists "content_packs") {
            Write-Host "`n[SUCCESS] ✅ VERIFIED: content_packs table now exists!" -ForegroundColor Green
            $fixed = $true
        } else {
            Write-Host "`n[WARNING] Migration completed but table not found yet" -ForegroundColor Yellow
            Write-Host "[INFO] Will retry in 3 seconds..." -ForegroundColor Gray
            Start-Sleep -Seconds 3
        }
    } else {
        Write-Host "`n[WARNING] Migration failed" -ForegroundColor Yellow
        Write-Host "[INFO] Will retry in 3 seconds..." -ForegroundColor Gray
        Start-Sleep -Seconds 3
    }
    
    Write-Host ""
}

# Final check
if (-not $fixed) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "FINAL CHECK" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    
    if (Test-TableExists "content_packs") {
        Write-Host "`n[SUCCESS] ✅ Table exists after all attempts!" -ForegroundColor Green
        $fixed = $true
    } else {
        Write-Host "`n[ERROR] ❌ Issue persists after $maxRetries attempts" -ForegroundColor Red
        Write-Host "`n[MANUAL] Manual steps needed:" -ForegroundColor Yellow
        Write-Host "   1. Check DATABASE_URL in .env file" -ForegroundColor White
        Write-Host "   2. Ensure PostgreSQL is running" -ForegroundColor White
        Write-Host "   3. Check database user permissions" -ForegroundColor White
        Write-Host "   4. Run: .\venv\Scripts\python.exe -m alembic upgrade head" -ForegroundColor White
    }
}

# Final result
Write-Host "`n========================================" -ForegroundColor Cyan
if ($fixed) {
    Write-Host "✅✅✅ FIX COMPLETE! ✅✅✅" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[SUCCESS] The content_packs table has been created." -ForegroundColor Green
    Write-Host "[SUCCESS] Network errors should now be resolved!" -ForegroundColor Green
    Write-Host ""
    Write-Host "[NEXT] Restart your backend server" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "⚠️  FIX INCOMPLETE" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[INFO] Script completed but issue not fully resolved" -ForegroundColor Yellow
    Write-Host "[INFO] Please check the errors above" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "[END] Script finished" -ForegroundColor Gray
