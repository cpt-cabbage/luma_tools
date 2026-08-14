Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"

Write-Output '=== farm isolation ==='
python\venv\Scripts\python.exe -m pytest tests\test_farm_isolation.py -q --no-header

Write-Output '=== full suite ==='
python\venv\Scripts\python.exe -m pytest tests\ -q --no-header

Write-Output '=== app launch (comfyui tab) ==='
python\venv\Scripts\python.exe python\core\luma_tools.py --tab comfyui --auto-close 20
Write-Output "app exit code: $LASTEXITCODE"
