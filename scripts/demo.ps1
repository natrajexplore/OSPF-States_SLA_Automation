# Run the dashboard in simulation mode on this PC without Docker: backend on :8010, UI on http://localhost:5173.
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
# Needs Python 3.11+ and Node 18+. Creates backend\.venv-demo the first time. Ctrl+C stops both.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root "backend\.venv-demo"
if (-not (Test-Path $venv)) {
    python -m venv $venv
    & "$venv\Scripts\python.exe" -m pip install -q -r (Join-Path $root "backend\requirements.txt")
}
$env:OSPF_SIMULATE = "true"
$env:OSPF_KAFKA_BOOTSTRAP = ""
$backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory (Join-Path $root "backend") `
    -FilePath "$venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010"
try {
    Push-Location (Join-Path $root "frontend")
    if (-not (Test-Path "node_modules")) { npm ci }
    $env:VITE_API = "http://127.0.0.1:8010"
    Write-Host "`nOpen http://localhost:5173  (simulation mode)`n" -ForegroundColor Green
    npx vite --port 5173
} finally {
    Pop-Location
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
}
