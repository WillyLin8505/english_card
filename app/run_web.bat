@echo off
rem Runs the app in Chrome with the AI tagging service's address and key
rem from tagging.local.json (start ..\tagger\start_tagger.bat first),
rem plus the PostHog analytics key from posthog.local.json when it exists.
cd /d "%~dp0"
set ANALYTICS=
if exist posthog.local.json set ANALYTICS=--dart-define-from-file=posthog.local.json
flutter run -d chrome --dart-define-from-file=tagging.local.json %ANALYTICS% %*
