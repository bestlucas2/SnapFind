param(
    [switch]$NoSeed,    # skip demo data seeding
    [int]$Port = 8000
)

# One-command setup + run for SnapFind.
#   .\run.ps1            set up everything and start the app (with demo data)
#   .\run.ps1 -NoSeed    start without seeding the demo account
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "==> Creating virtual environment (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "==> Installing dependencies..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt --quiet

if (-not (Test-Path ".env")) {
    Write-Host "==> Creating .env (SQLite + generated secret)..." -ForegroundColor Cyan
    $secret = (& $venvPy -c "import secrets; print(secrets.token_hex(32))").Trim()
    $lines = @(
        "SECRET_KEY=$secret",
        "DATABASE_URL=sqlite:///./snapfind.db",
        "APP_NAME=SnapFind",
        "DEBUG=true"
    )
    # ASCII avoids a UTF-8 BOM that would corrupt the first key for dotenv.
    Set-Content -Path ".env" -Value $lines -Encoding ascii
}

if (-not $NoSeed) {
    Write-Host "==> Seeding demo data (idempotent)..." -ForegroundColor Cyan
    & $venvPy -m seed.seed
}

if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Host "Note: Tesseract not found on PATH - OCR on new uploads will show 'Failed'" -ForegroundColor Yellow
    Write-Host "      until you install it (see README). The demo data works regardless." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> SnapFind running at http://localhost:$Port   (Ctrl+C to stop)" -ForegroundColor Green
& $venvPy -m uvicorn main:app --reload --port $Port
