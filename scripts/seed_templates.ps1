# Seed or update all templates from seed_templates.py
# Run from repo root: .\scripts\seed_templates.ps1
# Or with force to update existing: .\scripts\seed_templates.ps1 -Force

param([switch]$Force)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root

if ($Force) {
    Write-Host "Seeding templates (--force: update existing)..." -ForegroundColor Yellow
    python -m app.seed.cli --templates --force
} else {
    Write-Host "Seeding templates (new only; use -Force to update existing)..." -ForegroundColor Yellow
    python -m app.seed.cli --templates
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Seed failed. Ensure dependencies are installed: pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}
Write-Host "Done. Restart backend if needed; refresh frontend /templates to see all templates." -ForegroundColor Green
