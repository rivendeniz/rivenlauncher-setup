@echo off
cd /d "%~dp0"
python riven.py
if errorlevel 1 pause
