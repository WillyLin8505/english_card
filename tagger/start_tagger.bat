@echo off
rem Starts the 拍照學英文 photo-tagging API on http://127.0.0.1:8765/tag
rem (Ollama must be installed with qwen3.5:4b pulled).
rem The model runs in llama-server with 4 parallel slots (start_llm.py): Ollama
rem 0.35 serves qwen3.5 one request at a time. Ollama only supplies the binary
rem and the model file. For Ollama itself: set TAGGER_BACKEND=ollama,
rem TAGGER_ALLOW_OLLAMA=1 and TAGGER_PARALLEL=1, and skip start_llm.py.
rem Output goes to lexicon\logs\llm.log and tagger.log, not these windows (card #992):
rem a window whose output is not drained blocks the server on every request.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
rem TAGGER_* defaults live in tagger_config.py (card #70); set a var here only to override.
set LOGDIR=%~dp0..\lexicon\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for %%F in ("%LOGDIR%\llm.log" "%LOGDIR%\tagger.log") do if %%~zF GTR 50000000 move /y "%%~F" "%%~F.1" >nul
echo LLM output: %LOGDIR%\llm.log
echo Tagger output: %LOGDIR%\tagger.log
start "LLM server (llama-server, 4 slots)" cmd /k "python "%~dp0start_llm.py" >> "%LOGDIR%\llm.log" 2>&1"
python "%~dp0tagging_server.py" %* >> "%LOGDIR%\tagger.log" 2>&1
