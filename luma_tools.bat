@echo on

call %~dp0\python\venv\Scripts\activate.bat
cd /d %~dp0
set PYTHONPATH=%~dp0\python;%~dp0\resources\ui;%PYTHONPATH%
set AYON_DEFAULT_SETTINGS_VARIANT=LUMA-PRODUCTION-Bundle-2025-12-08-02
start /B python %~dp0\python\core\luma_tools.py %*
pause