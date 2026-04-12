@echo off
cd /d %~dp0
set PYTHONPATH=%~dp0\python;%~dp0\resources\ui;%PYTHONPATH%
start "" "%~dp0\python\venv\Scripts\pythonw.exe" "%~dp0\python\core\luma_tools.py"
