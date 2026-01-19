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
echo Update types:
echo   b = Big update    (0.4 -^> 0.5)
echo   s = Small update  (0.4 -^> 0.4.1, or 0.4.1 -^> 0.4.2)
echo   m = Minor update  (0.4.1 -^> 0.4.1.1, or 0.4.1.1 -^> 0.4.1.2)
echo   n = No version change (skip versioning and changelog)
echo.
set /p UPDATE_TYPE="Update type (b/s/m/n): "

REM Skip versioning and changelog if user chose 'n'
if /i "%UPDATE_TYPE%"=="n" (
    set NEW_VERSION=%CURRENT_VERSION%
    echo Skipping version increment and changelog update.
    echo.
    goto :skip_versioning
)

REM Increment version using PowerShell based on update type
if /i "%UPDATE_TYPE%"=="b" (
    for /f "usebackq delims=" %%v in (`powershell -Command "$v='%CURRENT_VERSION%'; $parts=$v.Split('.'); $newMinor=[int]$parts[1]+1; '{0}.{1}' -f $parts[0],$newMinor"`) do set NEW_VERSION=%%v
) else if /i "%UPDATE_TYPE%"=="s" (
    for /f "usebackq delims=" %%v in (`powershell -Command "$v='%CURRENT_VERSION%'; $parts=$v.Split('.'); if($parts.Count -eq 2){'{0}.{1}.1' -f $parts[0],$parts[1]}else{'{0}.{1}.{2}' -f $parts[0],$parts[1],([int]$parts[2]+1)}"`) do set NEW_VERSION=%%v
) else if /i "%UPDATE_TYPE%"=="m" (
    for /f "usebackq delims=" %%v in (`powershell -Command "$v='%CURRENT_VERSION%'; $parts=$v.Split('.'); if($parts.Count -le 3){$v+'.1'}else{$parts[3]=[int]$parts[3]+1; $parts -join '.'}"`) do set NEW_VERSION=%%v
) else (
    set NEW_VERSION=%CURRENT_VERSION%
)
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
    REM Write commit message to temp file to avoid escaping issues with special characters
    set "TEMP_MSG_FILE=%TEMP%\luma_commit_msg.txt"
    git log -1 --pretty=%%s > "!TEMP_MSG_FILE!"
    REM Use PowerShell to read from temp file and update changelog
    powershell -Command "$nl = [char]10; $msg = Get-Content '!TEMP_MSG_FILE!' -Raw; $msg = $msg.Trim(); $msg = $msg -replace ' -', ($nl + '-'); $changelog = Get-Content '%SOURCE%\changelog.md' -Raw; $header = '# Luma Tools Changelog'; $newEntry = $nl + $nl + '## Version %NEW_VERSION%' + $nl + $msg; $changelog = $changelog -replace [regex]::Escape($header), ($header + $newEntry); Set-Content '%SOURCE%\changelog.md' $changelog -NoNewline"
    del "!TEMP_MSG_FILE!" 2>nul
    echo Changelog updated.
) else (
    echo Changelog not updated.
)

echo.
echo Version updated to %NEW_VERSION%
echo.

:skip_versioning

REM Copy launcher batch files
echo Copying launchers...
REM Skipping luma_tools.bat - only copy standalone launcher
xcopy "%SOURCE%\luma_tools_standalone.bat" "%TARGET%\" /Y /Q
if errorlevel 1 (
    echo ERROR: Failed to copy launcher
    pause
    exit /b 1
)

REM Remove pause from launcher batch file in target
echo Removing pause from launcher...
powershell -Command "(Get-Content '%TARGET%\luma_tools_standalone.bat') | Where-Object { $_ -ne 'pause' } | Set-Content '%TARGET%\luma_tools_standalone.bat'"

REM ============================================================================
REM CLEAN ALL PYTHON FILES FOR FRESH INSTALL
REM ============================================================================

echo Cleaning all Python files from production for fresh install...

REM Remove all Python module directories (ensures no orphaned files)
if exist "%TARGET%\python\core\" (
    echo Removing old core module...
    rmdir /S /Q "%TARGET%\python\core\"
)
if exist "%TARGET%\python\ayon\" (
    echo Removing old ayon module...
    rmdir /S /Q "%TARGET%\python\ayon\"
)
if exist "%TARGET%\python\comfyui\" (
    echo Removing old comfyui module...
    rmdir /S /Q "%TARGET%\python\comfyui\"
)
if exist "%TARGET%\python\models\" (
    echo Removing old models module...
    rmdir /S /Q "%TARGET%\python\models\"
)
if exist "%TARGET%\python\services\" (
    echo Removing old services module...
    rmdir /S /Q "%TARGET%\python\services\"
)
if exist "%TARGET%\python\tabs\" (
    echo Removing old tabs module...
    rmdir /S /Q "%TARGET%\python\tabs\"
)
if exist "%TARGET%\python\ui\" (
    echo Removing old ui module...
    rmdir /S /Q "%TARGET%\python\ui\"
)
if exist "%TARGET%\python\libs\" (
    echo Removing old libs directory...
    rmdir /S /Q "%TARGET%\python\libs\"
)

REM Remove any stray Python files in python root directory
echo Removing any stray Python files in python root...
del /Q "%TARGET%\python\*.py" 2>nul
del /Q "%TARGET%\python\*.pyc" 2>nul
if exist "%TARGET%\python\__pycache__\" (
    rmdir /S /Q "%TARGET%\python\__pycache__\"
)

echo All old Python files cleaned.
echo.

REM ============================================================================
REM COPY NEW DOMAIN-BASED PYTHON PACKAGES
REM ============================================================================

REM Copy Python core module
echo Copying Python core module...
xcopy "%SOURCE%\python\core\*.py" "%TARGET%\python\core\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python core module
    pause
    exit /b 1
)

REM Copy Python ayon module
echo Copying Python ayon module...
xcopy "%SOURCE%\python\ayon\*.py" "%TARGET%\python\ayon\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python ayon module
    pause
    exit /b 1
)

REM Copy Python ayon validators
echo Copying Python ayon validators...
xcopy "%SOURCE%\python\ayon\validators\*.py" "%TARGET%\python\ayon\validators\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python ayon validators
    pause
    exit /b 1
)

REM Copy Python comfyui module
echo Copying Python comfyui module...
xcopy "%SOURCE%\python\comfyui\*.py" "%TARGET%\python\comfyui\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python comfyui module
    pause
    exit /b 1
)

REM Copy Python models module
echo Copying Python models module...
xcopy "%SOURCE%\python\models\*.py" "%TARGET%\python\models\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python models module
    pause
    exit /b 1
)

REM Copy Python services module
echo Copying Python services module...
xcopy "%SOURCE%\python\services\*.py" "%TARGET%\python\services\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python services module
    pause
    exit /b 1
)

REM Copy Python tabs module
echo Copying Python tabs module...
xcopy "%SOURCE%\python\tabs\*.py" "%TARGET%\python\tabs\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python tabs module
    pause
    exit /b 1
)

REM Copy Python ui module (shared UI components)
echo Copying Python ui module...
xcopy "%SOURCE%\python\ui\*.py" "%TARGET%\python\ui\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Python ui module
    pause
    exit /b 1
)

REM Copy Python libs (external binaries like Assimp DLL)
echo Copying Python libs...
xcopy "%SOURCE%\python\libs\*.*" "%TARGET%\python\libs\" /Y /Q /I /S
if errorlevel 1 (
    echo WARNING: Failed to copy Python libs (may not exist)
)

REM ============================================================================
REM COPY VIRTUAL ENVIRONMENT
REM ============================================================================

echo.
set /p UPDATE_VENV="Update virtual environment? (y/n): "
if /i not "%UPDATE_VENV%"=="y" (
    echo Skipping virtual environment update.
    goto :skip_venv
)

REM Check if source venv exists
if not exist "%SOURCE%\python\venv\" (
    echo WARNING: Source venv not found at %SOURCE%\python\venv\
    echo Skipping venv copy.
    goto :skip_venv
)

echo.
echo Copying virtual environment...
echo This may take a few minutes (approx 10,000+ files)...
echo.

REM Copy the entire venv directory (without /Q to show progress)
xcopy "%SOURCE%\python\venv\*.*" "%TARGET%\python\venv\" /E /Y /I /H
if errorlevel 1 (
    echo ERROR: Failed to copy virtual environment
    pause
    exit /b 1
)

echo.
echo Virtual environment copied successfully.

:skip_venv

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

REM Copy Three.js viewer HTML files
echo Copying Three.js viewer files...
xcopy "%SOURCE%\resources\threejs\*.html" "%TARGET%\resources\threejs\" /Y /Q /I
if errorlevel 1 (
    echo ERROR: Failed to copy Three.js viewer files
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
