# Point B: start face-picture receive server
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt | Out-Null

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created point_b/.env — set SYNC_TOKEN, then re-run."
    exit 1
}

python receive_server.py
