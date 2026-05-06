Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Running Chatbot Seeder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Set-Location $PSScriptRoot
python -m app.seed.cli --chatbots --force

Write-Host ""
Write-Host "Seeder completed!" -ForegroundColor Green
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
