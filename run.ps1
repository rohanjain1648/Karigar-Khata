# One-command local run (Windows PowerShell). First run installs everything and seeds demo data.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$root\backend"
if (-not (Test-Path .venv)) {
    uv venv .venv --python 3.12
    uv pip install -r requirements.txt --python .venv\Scripts\python.exe
}
if (-not (Test-Path data\khata.db)) { .venv\Scripts\python.exe -m app.seed }
Start-Process -NoNewWindow .venv\Scripts\python.exe -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000"

Set-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm install }
Write-Host "`n  Open http://127.0.0.1:5173  (demo split view: /demo)`n"
npx vite --host 127.0.0.1 --port 5173
