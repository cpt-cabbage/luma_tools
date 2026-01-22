@echo off
REM Install script - runs Python installer
REM Source: L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
REM Target: L:\tools\_studio_tools\luma_tools

set SOURCE=L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools

echo Running Luma Tools Installer...
echo.

"%SOURCE%\python\venv\Scripts\python.exe" "%SOURCE%\install.py"
