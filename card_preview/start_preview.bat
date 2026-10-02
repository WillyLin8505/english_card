@echo off
cd /d "%~dp0\.."
python card_preview\server.py --port 8772
pause
