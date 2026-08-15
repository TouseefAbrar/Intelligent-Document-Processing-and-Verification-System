# One-command launcher for Windows (PowerShell)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Creating backend venv if needed"
if (-not (Test-Path "$root\backend\.venv")) {
    python -m venv "$root\backend\.venv"
}

Write-Host "==> Installing backend dependencies"
& "$root\backend\.venv\Scripts\python.exe" -m pip install -r "$root\backend\requirements.txt" -q

Write-Host "==> Checking .env"
if (-not (Test-Path "$root\backend\.env")) {
    Copy-Item "$root\backend\.env.example" "$root\backend\.env"
    Write-Warning "Created backend/.env — please add your GROQ_API_KEY."
}

Write-Host "==> Installing frontend dependencies"
Push-Location "$root\frontend"
npm install --no-audit --no-fund | Out-Null
Pop-Location

Write-Host ""
Write-Host "Start with:"
Write-Host "  1) Backend :  cd $root\backend ; .venv\Scripts\python -m uvicorn app.main:app --reload"
Write-Host "  2) Frontend:  cd $root\frontend ; npm run dev"
Write-Host "  3) UI       :  http://localhost:5173"
