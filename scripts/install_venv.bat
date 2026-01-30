@echo off
echo ============================================================
echo Installing Python Virtual Environment
echo ============================================================
echo.
echo IMPORTANT: Close ALL instances of Luma Tools and any Python
echo processes before running this script!
echo.
pause

REM Navigate to project root (parent of scripts folder)
cd /d "%~dp0.."

REM Use system Python to run the install script
python scripts\install_venv.py %*

pause
