@echo off
setlocal enabledelayedexpansion
REM Install script - copies files to production location
REM Source: L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
REM Target: L:\tools\_studio_tools\luma_tools

set SOURCE=L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
set TARGET=L:\tools\_studio_tools\luma_tools
set DEV_PATH=L:/tools/_studio_tools/AYON/_dev/christophe/la_shot_tools/luma_tools
set PROD_PATH=L:/tools/_studio_tools/luma_tools

echo Installing Luma Tools to %TARGET%...
echo.

REM ============================================================================
REM VERSION INCREMENT AND CHANGELOG UPDATE
REM ============================================================================

echo Updating version and changelog...

REM Get current version from version.json using PowerShell
for /f "usebackq delims=" %%v in (`powershell -Command "(Get-Content '%SOURCE%\version.json' | ConvertFrom-Json).version"`) do set CURRENT_VERSION=%%v
echo Current version: %CURRENT_VERSION%

REM Prompt user for update type
echo.
set /p BIG_UPDATE="Big Update? (y/n): "
if /i "%BIG_UPDATE%"=="y" (
    set INCREMENT=0.1
    set DECIMALS=1
) else (
    set INCREMENT=0.01
    set DECIMALS=2
)

REM Increment version using PowerShell
for /f "usebackq delims=" %%v in (`powershell -Command "[math]::Round([decimal]'%CURRENT_VERSION%' + %INCREMENT%, %DECIMALS%)"`) do set NEW_VERSION=%%v
echo New version: %NEW_VERSION%

REM Update version.json with new version
powershell -Command "$json = Get-Content '%SOURCE%\version.json' | ConvertFrom-Json; $json.version = '%NEW_VERSION%'; $json | ConvertTo-Json | Set-Content '%SOURCE%\version.json'"

REM Get the last git commit message
cd /d "%SOURCE%"
for /f "usebackq delims=" %%m in (`git log -1 --pretty^=%%s`) do set COMMIT_MSG=%%m
echo.
echo Last git commit: %COMMIT_MSG%

REM Prompt user to update changelog
echo.
set /p UPDATE_CHANGELOG="Update changelog from git? (y/n): "
if /i "%UPDATE_CHANGELOG%"=="y" (
    REM Prepend new version entry to changelog.md (escape single quotes for PowerShell)
    set "COMMIT_MSG_ESCAPED=!COMMIT_MSG:'=''!"
    powershell -Command "$nl = [char]10; $msg = '!COMMIT_MSG_ESCAPED!'; if (-not $msg.StartsWith('- ')) { $msg = '- ' + $msg }; $changelog = Get-Content '%SOURCE%\changelog.md' -Raw; $header = '# Luma Tools Changelog'; $newEntry = $nl + $nl + '## Version %NEW_VERSION%' + $nl + $msg; $changelog = $changelog -replace [regex]::Escape($header), ($header + $newEntry); Set-Content '%SOURCE%\changelog.md' $changelog -NoNewline"
    echo Changelog updated with: %COMMIT_MSG%
) else (
    echo Changelog not updated.
)

echo.
echo Version updated to %NEW_VERSION%
echo.

REM Copy launcher batch files
echo Copying launchers...
xcopy "%SOURCE%\luma_tools.bat" "%TARGET%\" /Y /Q
xcopy "%SOURCE%\luma_tools_standalone.bat" "%TARGET%\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy launcher
    pause
    exit /b 1
)

REM Remove pause from launcher batch files in target
echo Removing pause from launchers...
powershell -Command "(Get-Content '%TARGET%\luma_tools.bat') | Where-Object { $_ -ne 'pause' } | Set-Content '%TARGET%\luma_tools.bat'"
powershell -Command "(Get-Content '%TARGET%\luma_tools_standalone.bat') | Where-Object { $_ -ne 'pause' } | Set-Content '%TARGET%\luma_tools_standalone.bat'"

REM Copy Python files (root)
echo Copying Python files...
xcopy "%SOURCE%\python\*.py" "%TARGET%\python\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy Python files
    pause
    exit /b 1
)

REM Copy Python tabs module
echo Copying Python tabs module...
xcopy "%SOURCE%\python\tabs\*.py" "%TARGET%\python\tabs\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy Python tabs module
    pause
    exit /b 1
)

REM Copy UI resources (root)
echo Copying UI resources...
xcopy "%SOURCE%\resources\ui\*.ui" "%TARGET%\resources\ui\" /Y /Q
xcopy "%SOURCE%\resources\ui\*.qss" "%TARGET%\resources\ui\" /Y /Q
xcopy "%SOURCE%\resources\ui\*.py" "%TARGET%\resources\ui\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy UI files
    pause
    exit /b 1
)

REM Copy tab UI files
echo Copying tab UI files...
xcopy "%SOURCE%\resources\ui\tabs\*.ui" "%TARGET%\resources\ui\tabs\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy tab UI files
    pause
    exit /b 1
)

REM Copy icons
echo Copying icons...
xcopy "%SOURCE%\resources\icons\*.svg" "%TARGET%\resources\icons\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy icons
    pause
    exit /b 1
)

REM Copy image resources (logo, etc.)
echo Copying image resources...
xcopy "%SOURCE%\resources\*.png" "%TARGET%\resources\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy image resources
    pause
    exit /b 1
)

REM Copy and update global settings (replace dev paths with production paths)
echo Copying and updating global settings...
xcopy "%SOURCE%\global_settings\*.json" "%TARGET%\global_settings\" /Y /Q

REM Update paths in global_settings.json (replace dev paths with production paths)
echo Updating paths in global_settings.json...
powershell -Command "(Get-Content '%TARGET%\global_settings\global_settings.json') -replace '%DEV_PATH%', '%PROD_PATH%' | Set-Content '%TARGET%\global_settings\global_settings.json'"
if errorlevel 1 (
    echo WARNING: Failed to update paths in global_settings.json
)

REM Copy version and changelog files
echo Copying version and changelog files...
xcopy "%SOURCE%\version.json" "%TARGET%\" /Y /Q
xcopy "%SOURCE%\changelog.md" "%TARGET%\" /Y /Q
if errorlevel 1 (
    echo WARNING: Failed to copy version/changelog files
)

echo.
echo Installation complete! Version %NEW_VERSION% deployed.
pause
