@echo off
REM Seed or update all templates. Run from repo root: scripts\seed_templates.bat
REM To update existing templates too, run: scripts\seed_templates.bat --force
cd /d "%~dp0\.."
if "%~1"=="--force" (
    python -m app.seed.cli --templates --force
) else (
    python -m app.seed.cli --templates
)
if errorlevel 1 (
    echo Seed failed. Install deps: pip install -r requirements.txt
    exit /b 1
)
echo Done. Restart backend if needed; refresh frontend /templates to see all templates.
