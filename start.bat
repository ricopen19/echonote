@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo Starting Ollama...
start "" /min ollama serve

echo Waiting for Ollama...
timeout /t 4 /nobreak > nul

echo Starting Echonote...
uv run echonote

pause
