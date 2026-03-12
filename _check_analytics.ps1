Set-Location 'L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools'

# Check user settings for workflow times
$settingsPath = Join-Path $env:USERPROFILE '.luma_tools\settings.json'
if (Test-Path $settingsPath) {
    Write-Host "=== Stored Workflow Execution Times ==="
    $json = Get-Content $settingsPath -Raw | ConvertFrom-Json
    if ($json.comfyui_workflow_times) {
        $json.comfyui_workflow_times | ConvertTo-Json -Depth 5
    } else {
        Write-Host "No comfyui_workflow_times key found in settings"
    }
} else {
    Write-Host "Settings file not found at $settingsPath"
}

Write-Host ""

# Show ALL log files from today (most recent first)
Write-Host "=== Log files ==="
Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' -Filter '*20260207*' | Sort-Object LastWriteTime -Descending | Select-Object -First 3 | ForEach-Object {
    Write-Host "$($_.Name) - LastWrite: $($_.LastWriteTime)"
}

Write-Host ""

# Search latest log for submission and completion events
$logFile = Get-ChildItem 'W:\LumaRND\luma_tools\_logs\users\' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "=== Key events in $($logFile.Name) ==="
$patterns = 'Starting polling|Merged.*batch|batch_jobs_completed|iterate_job_completed|Recorded.*per frame|Copied runner|Copied utils|Copied analytics|submission complete'
Select-String -Path $logFile.FullName -Pattern $patterns | ForEach-Object { $_.Line }

Write-Host ""

# Show latest 3 execution records
$execDir = 'W:\LumaRND\luma_tools\_analytics\executions'
$files = Get-ChildItem $execDir -Filter '*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Write-Host "=== Latest $($files.Count) Execution Records ==="
foreach ($f in $files) {
    Write-Host ""
    Write-Host "--- $($f.Name) ---"
    Get-Content $f.FullName
}
