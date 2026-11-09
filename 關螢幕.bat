@echo off
rem Turn the screen off; dispatch, Qwen and the API keep running. Move the mouse or press a key to bring it back.
rem Works from the repo or from a copy elsewhere (e.g. the Desktop). Add -Check to only test the script.
set "PS1=%~dp0lexicon\tools\screen_off.ps1"
if not exist "%PS1%" set "PS1=D:\vibe_coding\english_card\lexicon\tools\screen_off.ps1"
if not exist "%PS1%" (
  echo screen_off.ps1 not found: %PS1%
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%PS1%" %*
