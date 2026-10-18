@echo off
cd /d "%~dp0"
python start_services.py
if errorlevel 1 pause
