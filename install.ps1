# Dot-source this file:  . .\install.ps1
# Creates the venv on first run, activates it, and installs dev dependencies.
# On subsequent runs, just activates the existing venv.

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path .venv\Scripts\Activate.ps1)) {
    Write-Host "Creating venv..."
    python -m venv .venv
    Write-Host "Activating venv..."
    .\.venv\Scripts\Activate.ps1
    Write-Host "Installing dev dependencies..."
    pip install -e '.[dev,gui,tui]'
    Write-Host "Done. Ready to develop."
} else {
    Write-Host "Activating venv..."
    .\.venv\Scripts\Activate.ps1
    Write-Host "Ready."
}
