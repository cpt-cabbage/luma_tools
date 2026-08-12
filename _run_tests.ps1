param([string]$TestArgs = "tests\")
Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"
$argList = $TestArgs -split ' '
& python\venv\Scripts\python.exe -m pytest @argList -q
