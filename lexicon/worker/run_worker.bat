@echo off
rem Runs one worker lane and starts it again when it exits (#285):
rem   exit 3  = backend code changed on disk -> restart now with the new code
rem   exit 0  = stopped on purpose (Ctrl+C) -> stay stopped
rem   other   = crashed (e.g. a half-saved file) -> try again in 30 s
rem Usage: worker\run_worker.bat text|images|tags|all
rem Output goes to logs\worker_<lane>.log, not this window (card #992): a window whose
rem output is not drained (a stalled terminal tab, a selection in the window) blocks the
rem worker on every print, the same hang that froze the API (card #990).
cd /d "%~dp0.."
set PYTHONUNBUFFERED=1
if not exist logs mkdir logs
set LOG=logs\worker_%1.log
echo Worker output: %CD%\%LOG%
:loop
for %%F in (%LOG%) do if %%~zF GTR 50000000 move /y %LOG% %LOG%.1 >nul
python worker\worker.py --lane %1 >> %LOG% 2>&1
set code=%errorlevel%
if "%code%"=="0" goto :eof
if "%code%"=="3" (
  timeout /t 2 /nobreak >nul
  goto loop
)
echo Worker exited with code %code%; see %LOG%; restarting in 30 s (close this window to stop).
timeout /t 30 /nobreak >nul
goto loop
