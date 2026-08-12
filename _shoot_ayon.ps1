# Capture UI screenshots into .ui-ayon/<set>/
#
#   powershell -ExecutionPolicy Bypass -File _shoot_ayon.ps1 before
#   powershell -ExecutionPolicy Bypass -File _shoot_ayon.ps1 L1 tabs,zoo
#
# Arg 1: set name (subdirectory under .ui-ayon/). Default "current".
# Arg 2: comma-separated scenarios. Default: all.
#        tabs, zoo, settings, comfyui, gallery, cleaner, renders
#
# Shot context (jobname/shot/task/shotpath/user/subdir) is set in
# scripts/ui_ayon.py -> SHOT_CONTEXT.
param(
    [string]$Set = "current",
    [string]$Scenarios = ""
)

Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'
$env:PYTHONPATH = "$(Get-Location)\python;$(Get-Location)\resources\ui"

$out = Join-Path (Get-Location) ".ui-ayon\$Set"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $out | Out-Null

python\venv\Scripts\python.exe scripts\ui_ayon.py $out $Scenarios

Write-Output ""
Write-Output "=== harness log ==="
$log = Join-Path $out "_harness.log"
if (Test-Path $log) { Get-Content $log } else { Write-Output "(no harness log written)" }
Write-Output ""
Write-Output "=== captured ==="
Get-ChildItem $out -Filter *.png | Select-Object Name, Length | Format-Table -AutoSize
