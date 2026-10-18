@echo off
rem Starts the lexicon admin: API (8770), workers, and admin UI (5173).
rem First time: see README.md (PostgreSQL, .env, migration, npm install).
rem Workers run in lanes so network, model and picture work overlap: four
rem text workers and three picture labellers share the model server's four
rem slots (tagger\start_tagger.bat); two download pictures from Wikimedia.
cd /d "%~dp0"
python -m alembic upgrade head || goto :error
start "lexicon API" cmd /k python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8770
start "lexicon text 1" cmd /k python worker\worker.py --lane text
start "lexicon text 2" cmd /k python worker\worker.py --lane text
start "lexicon text 3" cmd /k python worker\worker.py --lane text
start "lexicon text 4" cmd /k python worker\worker.py --lane text
start "lexicon images 1" cmd /k python worker\worker.py --lane images
start "lexicon images 2" cmd /k python worker\worker.py --lane images
start "lexicon picture labels 1" cmd /k python worker\worker.py --lane tags
start "lexicon picture labels 2" cmd /k python worker\worker.py --lane tags
start "lexicon picture labels 3" cmd /k python worker\worker.py --lane tags
start "lexicon UI" cmd /k npm --prefix frontend run dev
timeout /t 4 >nul
start "" http://127.0.0.1:5173/ui/
goto :eof
:error
echo Migration failed. Is PostgreSQL running and lexicon\.env filled in?
pause
