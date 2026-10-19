@echo off
rem Runs the API (8770) and starts it again when it exits (#335):
rem   exit 3  = backend code changed on disk -> restart now with the new code
rem   exit 0  = stopped on purpose (Ctrl+C) -> stay stopped
rem   other   = crashed (e.g. a half-saved file) -> try again in 30 s
cd /d "%~dp0"
set LEXICON_API_AUTORESTART=1
:loop
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8770
set code=%errorlevel%
if "%code%"=="0" goto :eof
if "%code%"=="3" (
  timeout /t 2 /nobreak >nul
  goto loop
)
echo API exited with code %code%; restarting in 30 s (close this window to stop).
timeout /t 30 /nobreak >nul
goto loop
