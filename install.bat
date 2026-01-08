@echo off
REM Install script - copies files to production location
REM Source: L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
REM Target: L:\tools\_studio_tools\luma_tools

set SOURCE=L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
set TARGET=L:\tools\_studio_tools\luma_tools
set DEV_PATH=L:/tools/_studio_tools/AYON/_dev/christophe/la_shot_tools/luma_tools
set PROD_PATH=L:/tools/_studio_tools/luma_tools

echo Installing Luma Tools to %TARGET%...
echo.

REM Copy launcher batch file
echo Copying launcher...
xcopy "%SOURCE%\luma_tools.bat" "%TARGET%\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy launcher
    pause
    exit /b 1
)

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

echo.
echo Installation complete!
pause
