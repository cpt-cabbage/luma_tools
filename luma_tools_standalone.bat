@echo off
cd /d %~dp0
set PYTHONPATH=%~dp0\python;%~dp0\resources\ui;%PYTHONPATH%
set AYON_DEFAULT_SETTINGS_VARIANT=LUMA-PRODUCTION-Bundle-2025-12-08-02
start "" "%~dp0\python\venv\Scripts\pythonw.exe" "%~dp0\python\core\luma_tools.py"
