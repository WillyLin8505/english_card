@echo off
rem Turn the screen off; dispatch, Qwen and the API keep running. Move the mouse or press a key to bring it back.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0lexicon\tools\screen_off.ps1"
