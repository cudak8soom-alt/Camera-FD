# Point A — start camera inbox (receives face pictures from the camera)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== Point A camera inbox ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python not found. Install Python 3.10+ and tick 'Add Python to PATH'." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path .venv)) {
    Write-Host "First run: creating virtualenv..."
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip install failed." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env — fill camera settings, save, then run again." -ForegroundColor Yellow
    notepad .env
    exit 1
}

Write-Host "Starting camera inbox. Leave this window open. Ctrl+C to stop."
Write-Host "Pictures save under:  output\faces_camera\"
Write-Host ""
python serve.py
