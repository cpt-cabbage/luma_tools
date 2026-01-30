# Navigate to project root (parent of scripts folder)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "Installing Python Virtual Environment" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT: Close ALL instances of Luma Tools and any Python"
Write-Host "processes before running this script!"
Write-Host ""
Write-Host "Press Enter to continue..."
$null = Read-Host

# Use system Python to run the install script
# Pass through any arguments (--clean, --verify-only, --skip-optional)
python scripts/install_venv.py $args
