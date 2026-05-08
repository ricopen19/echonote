@echo off
chcp 65001 > nul
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1"
pause
