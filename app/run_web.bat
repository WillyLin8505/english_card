@echo off
rem Runs the app in Chrome with the AI tagging service's address and key
rem from tagging.local.json (start ..\tagger\start_tagger.bat first).
cd /d "%~dp0"
flutter run -d chrome --dart-define-from-file=tagging.local.json %*
