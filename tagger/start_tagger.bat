@echo off
rem Starts the 拍照學英文 photo-tagging API on http://127.0.0.1:8765/tag
rem (Ollama must be running with qwen3-vl:4b-instruct-q4_K_M pulled).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set TAGGER_NUM_CTX=4096
set TAGGER_NUM_PREDICT=600
set TAGGER_IMAGE_MAX_EDGE=768
set TAGGER_JPEG_QUALITY=70
set TAGGER_CEFR_NUM_PREDICT=1000
set TAGGER_KEEP_ALIVE=-1
python "%~dp0tagging_server.py" %*
