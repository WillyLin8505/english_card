@echo off
rem Runs one worker lane and starts it again when it exits (#285):
rem   exit 3  = backend code changed on disk -> restart now with the new code
rem   exit 0  = stopped on purpose (Ctrl+C) -> stay stopped
rem   other   = crashed (e.g. a half-saved file) -> try again in 30 s
rem Usage: worker\run_worker.bat text|images|tags|all
cd /d "%~dp0.."
:loop
python worker\worker.py --lane %1
set code=%errorlevel%
if "%code%"=="0" goto :eof
if "%code%"=="3" (
  timeout /t 2 /nobreak >nul
  goto loop
)
echo Worker exited with code %code%; restarting in 30 s (close this window to stop).
timeout /t 30 /nobreak >nul
goto loop
