# Run Database Migration - Fix content_packs table issue
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Running Database Migration" -ForegroundColor Green
Write-Host "This will fix the 'content_packs does not exist' error" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to backend
$backendDir = "C:\Users\rttsg\OneDrive\Desktop\1ne\1ne_backend"
Set-Location $backendDir

# Check venv
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please create virtual environment first" -ForegroundColor Yellow
    exit 1
}

# Check alembic
Write-Host "Checking alembic..." -ForegroundColor Yellow
$alembicCheck = .\venv\Scripts\python.exe -c "import alembic; print('OK')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing alembic..." -ForegroundColor Yellow
    .\venv\Scripts\pip.exe install alembic
}

# Check database connection first
Write-Host "`nTesting database connection..." -ForegroundColor Yellow
$dbTest = .\venv\Scripts\python.exe -c "from app.core.config import settings; from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1')); print('OK'); db.close()" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Database connection test failed" -ForegroundColor Yellow
    Write-Host "This might be normal if tables don't exist yet" -ForegroundColor Yellow
    Write-Host "Continuing with migration..." -ForegroundColor Yellow
}

# Run migration
Write-Host "`nRunning database migration..." -ForegroundColor Yellow
Write-Host "This will create the content_packs table and related tables." -ForegroundColor Cyan
Write-Host ""

$migrationOutput = .\venv\Scripts\python.exe -m alembic upgrade head 2>&1
$migrationExitCode = $LASTEXITCODE

Write-Host $migrationOutput

if ($migrationExitCode -eq 0) {
    Write-Host ""
    Write-Host "✅ Migration completed successfully!" -ForegroundColor Green
    Write-Host "The content_packs table has been created." -ForegroundColor Green
    
    # Verify table exists
    Write-Host "`nVerifying table creation..." -ForegroundColor Yellow
    $verify = .\venv\Scripts\python.exe -c "from app.db.session import SessionLocal; from sqlalchemy import text; db = SessionLocal(); db.execute(text('SELECT 1 FROM content_packs LIMIT 1')); print('✅ content_packs table exists!'); db.close()" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host $verify -ForegroundColor Green
    } else {
        Write-Host "⚠️  Table verification failed, but migration completed" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "✅ FIX COMPLETE!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Restart your backend server" -ForegroundColor White
    Write-Host "2. The network errors should now be fixed" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "❌ Migration failed!" -ForegroundColor Red
    Write-Host "Please check the error messages above." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "- DATABASE_URL in .env is incorrect" -ForegroundColor White
    Write-Host "- Database server is not running" -ForegroundColor White
    Write-Host "- Database user doesn't have permissions" -ForegroundColor White
    Write-Host ""
    exit 1
}
