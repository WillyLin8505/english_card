@echo off
rem Restart the Windows desktop compositor (dwm.exe) to release its leaked graphics memory.
rem The screen goes black for 1-2 seconds; all programs keep running. Asks for administrator rights (UAC).
powershell -NoProfile -Command "Start-Process taskkill -ArgumentList '/f','/im','dwm.exe' -Verb RunAs -WindowStyle Hidden"
