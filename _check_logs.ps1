Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"

# 10 back-to-back launches to test stability
for ($i = 1; $i -le 10; $i++) {
    Write-Host "=== Run $i ==="
    python\venv\Scripts\python.exe python\core\luma_tools.py --auto-close 10 2>&1
    Write-Host "Exit: $LASTEXITCODE"
}
