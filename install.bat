@echo off
REM Install script - copies files to production location
REM Source: L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
REM Target: L:\tools\_studio_tools\luma_tools

set SOURCE=L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
set TARGET=L:\tools\_studio_tools\luma_tools

echo Installing Luma Tools to %TARGET%...
echo.

REM Copy Python files
echo Copying Python files...
xcopy "%SOURCE%\python\*.py" "%TARGET%\python\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy Python files
    pause
    exit /b 1
)

REM Copy UI files
echo Copying UI files...
xcopy "%SOURCE%\resources\ui\*.ui" "%TARGET%\resources\ui\" /Y /Q
xcopy "%SOURCE%\resources\ui\*.qss" "%TARGET%\resources\ui\" /Y /Q
xcopy "%SOURCE%\resources\ui\*.py" "%TARGET%\resources\ui\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy UI files
    pause
    exit /b 1
)

REM Copy global settings
echo Copying global settings...
xcopy "%SOURCE%\global_settings\*.json" "%TARGET%\global_settings\" /Y /Q

echo.
echo Installation complete!
pause
