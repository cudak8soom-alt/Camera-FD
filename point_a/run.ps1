# Point A — send face pictures to Point B (run AFTER run_camera.ps1)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== Point A sync (send pictures to Point B) ===" -ForegroundColor Cyan
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
    Write-Host "Created .env — fill section 2 (SITE_ID, POINT_B_URL, SYNC_TOKEN), then re-run." -ForegroundColor Yellow
    notepad .env
    exit 1
}

$envText = Get-Content .env -Raw
if ($envText -match "100\.x\.x\.x" -or $envText -match "paste_token_here") {
    Write-Host "Point B settings in .env still look like examples." -ForegroundColor Yellow
    Write-Host "Fill SITE_ID, POINT_B_URL, SYNC_TOKEN — then save and run again."
    notepad .env
    exit 1
}

Write-Host "Starting sync. Leave this window open. Ctrl+C to stop."
Write-Host "(Camera inbox should already be running in another window.)"
Write-Host ""
python sync_to_b.py
