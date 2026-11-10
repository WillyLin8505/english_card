@echo off
rem Runs the API (8770) and starts it again when it exits (#335):
rem   exit 3  = backend code changed on disk -> restart now with the new code
rem   exit 0  = stopped on purpose (Ctrl+C) -> stay stopped
rem   other   = crashed (e.g. a half-saved file) -> try again in 30 s
rem Output goes to logs\api.log, not this window (card #990): uvicorn writes its access log
rem on the event loop, so a console that stops taking output (a stalled terminal tab, a
rem selection in the window) froze every request with the port still open, and each restart
rem threw away the only log. Stall dumps: logs\api_hang\.
cd /d "%~dp0"
set LEXICON_API_AUTORESTART=1
set PYTHONUNBUFFERED=1
if not exist logs mkdir logs
echo API output: %~dp0logs\api.log
:loop
for %%F in (logs\api.log) do if %%~zF GTR 50000000 move /y logs\api.log logs\api.log.1 >nul
python toolsetention_purge.py >> logsetention_purge.log 2>&1
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8770 >> logs\api.log 2>&1
set code=%errorlevel%
if "%code%"=="0" goto :eof
if "%code%"=="3" (
  timeout /t 2 /nobreak >nul
  goto loop
)
echo API exited with code %code%; restarting in 30 s (close this window to stop).
timeout /t 30 /nobreak >nul
goto loop
