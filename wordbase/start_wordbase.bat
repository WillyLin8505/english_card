@echo off
rem 單字資料庫：http://127.0.0.1:8771/  (pip install wn wordfreq opencc-python-reimplemented)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
start "" http://127.0.0.1:8771/
python "%~dp0server.py" %*
