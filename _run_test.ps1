Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
python\venv\Scripts\python.exe python\core\luma_tools.py --tab comfyui --auto-close 20
