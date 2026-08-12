# Gallery scalability benchmark / layout regression check.
#
#   powershell -ExecutionPolicy Bypass -File tests\benchmarks\run_gallery_bench.ps1
#   powershell -ExecutionPolicy Bypass -File tests\benchmarks\run_gallery_bench.ps1 -Script verify_gallery_layout.py
#   powershell -ExecutionPolicy Bypass -File tests\benchmarks\run_gallery_bench.ps1 -BenchArgs "--counts 2500 --view stacked --job-size 1"
#
# Both scripts create their own temp directory of placeholder PNGs; nothing
# touches the network share. They open a real window, so do not run them on a
# headless box.
param(
    [string]$Script = "bench_gallery.py",
    [string]$BenchArgs = "--counts 500,1000,2500,5000 --view grid"
)
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:PYTHONPATH = "$repo\python;$repo\resources\ui"
$env:QT_IMAGEIO_MAXALLOC = "2048"
Set-Location $PSScriptRoot
$argList = $BenchArgs -split ' '
if ($Script -eq "verify_gallery_layout.py") {
    & "$repo\python\venv\Scripts\python.exe" (Join-Path $PSScriptRoot $Script)
} else {
    & "$repo\python\venv\Scripts\python.exe" (Join-Path $PSScriptRoot $Script) @argList
}
