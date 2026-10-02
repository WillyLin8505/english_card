@echo off
rem Starts the lexicon admin: API (8770), four workers, and admin UI (5173).
rem First time: see README.md (PostgreSQL, .env, migration, npm install).
cd /d "%~dp0"
python -m alembic upgrade head || goto :error
start "lexicon API" cmd /k python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8770
start "lexicon worker 1" cmd /k python worker\worker.py
start "lexicon worker 2" cmd /k python worker\worker.py
start "lexicon worker 3" cmd /k python worker\worker.py
start "lexicon worker 4" cmd /k python worker\worker.py
start "lexicon UI" cmd /k npm --prefix frontend run dev
timeout /t 4 >nul
start "" http://127.0.0.1:5173/ui/
goto :eof
:error
echo Migration failed. Is PostgreSQL running and lexicon\.env filled in?
pause
