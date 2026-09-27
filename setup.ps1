# One-time setup on Windows: virtual environment, dependencies, fonts, tests.
# Run from the repository root:  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    py -3.12 -m venv .venv
    if (-not $?) { python -m venv .venv }
}
$py = ".venv\Scripts\python.exe"

Write-Host "Installing dependencies ..."
& $py -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "Downloading openly licensed fonts (about 50 MB, once) ..."
& $py -m pvm fonts
if ($LASTEXITCODE -ne 0) { throw "font download failed" }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example; add your API keys there."
}

Write-Host "Running tests ..."
& $py -m unittest discover -s tests -t .
if ($LASTEXITCODE -ne 0) { throw "tests failed" }
Write-Host "Ready. Try:  .venv\Scripts\python -m pvm --help"
