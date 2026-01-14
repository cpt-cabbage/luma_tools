@echo off

call %~dp0\python\venv\Scripts\activate.bat
cd /d %~dp0
set PYTHONPATH=%~dp0\python;%~dp0\resources\ui;%PYTHONPATH%
start /B python %~dp0\python\core\luma_tools.py
pause
