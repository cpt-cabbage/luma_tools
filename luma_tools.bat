@echo on

call %~dp0\python\venv\Scripts\activate.bat
python %~dp0\python\luma_tools.py %*
pause