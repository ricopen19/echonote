@echo off
chcp 65001 > nul
cd /d "%~dp0"

rem venv の onnxruntime DLL をシステム PATH より優先させる（ORT バージョン競合回避）
set "PATH=%~dp0.venv\Lib\site-packages\onnxruntime\capi;%PATH%"

echo Starting Ollama...
start "" /min ollama serve

echo Waiting for Ollama...
timeout /t 4 /nobreak > nul

echo Starting Echonote...
uv run --extra diarization --extra moonshine echonote

pause
