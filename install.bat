@echo off
REM Install script - copies files to production location
REM Source: L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
REM Target: L:\tools\_studio_tools\luma_tools

set SOURCE=L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
set TARGET=L:\tools\_studio_tools\luma_tools

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

REM Copy global settings
echo Copying global settings...
xcopy "%SOURCE%\global_settings\*.json" "%TARGET%\global_settings\" /Y /Q

echo.
echo Installation complete!
pause
