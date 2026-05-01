# Echonote セットアップスクリプト

Set-StrictMode -Version Latest
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ── 管理者権限がなければ自動で昇格して再起動 ──────────────────────────────────
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "管理者権限で再起動します..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# ── エラー時もウィンドウを閉じない ────────────────────────────────────────────
trap {
    Write-Host ""
    Write-Host "エラーが発生しました:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Read-Host "Enter キーを押すと終了します"
    exit 1
}

# ── ヘルパー関数 ──────────────────────────────────────────────────────────────
function Refresh-Path {
    $env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Install-WingetPackage {
    param([string]$Id, [string]$Name)
    Write-Host ""
    Write-Host "[$Name] インストール中..." -ForegroundColor Cyan
    winget install --id $Id --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) {
        Write-Host "[$Name] OK" -ForegroundColor Green
    } else {
        Write-Host "[$Name] スキップ（インストール済みの可能性があります）" -ForegroundColor Yellow
    }
}

# ── 作業ディレクトリをechonoteルートに設定 ────────────────────────────────────
$rootDir = Split-Path $PSScriptRoot -Parent
Set-Location $rootDir
Write-Host "作業ディレクトリ: $rootDir" -ForegroundColor Gray

# ── 1. winget で各ツールをインストール ─────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " ステップ 1/4: 必要なツールをインストール" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Install-WingetPackage "Python.Python.3.12"  "Python 3.12"
Install-WingetPackage "Gyan.FFmpeg"         "ffmpeg"
Install-WingetPackage "Ollama.Ollama"       "Ollama"
Install-WingetPackage "Git.Git"             "Git"

# ── 2. PATH を更新 ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " ステップ 2/4: PATH を更新" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Refresh-Path

# ffmpeg が winget でPATHに入らなかった場合の補完
foreach ($p in @("C:\Program Files\ffmpeg\bin", "C:\ffmpeg\bin")) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*ffmpeg*")) {
        $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        [Environment]::SetEnvironmentVariable("Path", $machinePath + ";" + $p, "Machine")
        $env:PATH += ";" + $p
        Write-Host "ffmpeg PATH を追加しました: $p" -ForegroundColor Green
    }
}

foreach ($cmd in @("python", "ffmpeg", "ollama")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        Write-Host "$cmd : OK" -ForegroundColor Green
    } else {
        Write-Host "$cmd : 見つかりません（セットアップ後に再起動してください）" -ForegroundColor Yellow
    }
}

# ── 3. uv と依存パッケージをインストール ───────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " ステップ 3/4: Echonote の依存パッケージをインストール" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

python -m pip install uv --quiet
Write-Host "uv : OK" -ForegroundColor Green

uv sync
Write-Host "依存パッケージ : OK" -ForegroundColor Green

# ── 4. Ollama モデルのダウンロード（確認あり） ────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " ステップ 4/4: LLM モデルのダウンロード" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "文字起こし結果を構造化するための AI モデル（約 2.5GB）をダウンロードします。" -ForegroundColor White
Write-Host "ダウンロードにはネット環境と数分〜十数分かかります。" -ForegroundColor Gray
Write-Host ""
$answer = Read-Host "ダウンロードしますか？ [y/N]"
if ($answer -match "^[yY]$") {
    Write-Host "ダウンロード中... しばらくお待ちください" -ForegroundColor Cyan
    ollama pull qwen3:4b-q4_K_M
    Write-Host "モデル : OK" -ForegroundColor Green
} else {
    Write-Host "スキップしました。後で 'ollama pull qwen3:4b-q4_K_M' を実行してください。" -ForegroundColor Yellow
}

# ── 完了 ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " セットアップ完了！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "PC を再起動してから start.bat をダブルクリックして起動してください。" -ForegroundColor White
Write-Host ""
Read-Host "Enter キーを押すと終了します"
