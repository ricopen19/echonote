@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo Ollama を起動中...
start /min "" ollama serve

echo 起動を待機中...
timeout /t 4 /nobreak > nul

echo Echonote を起動中...
uv run echonote

pause
