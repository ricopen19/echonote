@echo off
chcp 65001 > nul
echo Echonote セットアップを開始します...
echo 管理者権限の確認ダイアログが表示されたら「はい」をクリックしてください。
echo.
powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"%~dp0scripts\setup.ps1\"' -Verb RunAs"
