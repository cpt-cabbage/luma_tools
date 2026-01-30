@echo off
REM Deploy script - deploys Luma Tools to production
REM Source: L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools
REM Target: L:\tools\_studio_tools\luma_tools

set SOURCE=L:\tools\_studio_tools\AYON\_dev\christophe\la_shot_tools\luma_tools

echo Running Luma Tools Deployment...
echo.

"%SOURCE%\python\venv\Scripts\python.exe" "%SOURCE%\scripts\deploy.py"
