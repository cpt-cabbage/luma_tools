@echo on

call %~dp0\python\venv\Scripts\activate.bat
start /B python %~dp0\python\luma_tools.py %*