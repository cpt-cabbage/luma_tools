$dirs = Get-ChildItem 'W:\LumaRND\luma_tools\christophe.leyder\_job_data' -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$wf = Get-ChildItem $dirs.FullName -Filter 'comfyui_workflow*.json' | Select-Object -First 1
Write-Output $wf.FullName
