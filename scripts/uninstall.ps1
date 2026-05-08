# Echonote Uninstall Script

# --- Elevate to admin if needed ---
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -ArgumentList ('-ExecutionPolicy Bypass -File "' + $PSCommandPath + '"') -Verb RunAs
    exit
}

try {

    $rootDir = Split-Path $PSScriptRoot -Parent
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Echonote Uninstaller" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "以下を削除します:" -ForegroundColor White
    Write-Host "  - Python 仮想環境 (.venv)" -ForegroundColor Gray
    Write-Host "  - Whisper モデルキャッシュ (~/.cache/huggingface)" -ForegroundColor Gray
    Write-Host "  - Ollama モデル (qwen3:4b-q4_K_M)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "続けますか？ [y/N]" -ForegroundColor Yellow -NoNewline
    $confirm = Read-Host " "
    if ($confirm -notmatch "^[yY]$") {
        Write-Host "キャンセルしました。" -ForegroundColor Yellow
        exit
    }

    # --- Step 1: Delete .venv ---
    Write-Host ""
    Write-Host "Step 1/3: 仮想環境を削除中..." -ForegroundColor Yellow
    $venvPath = Join-Path $rootDir ".venv"
    if (Test-Path $venvPath) {
        Remove-Item $venvPath -Recurse -Force
        Write-Host "  .venv: 削除完了" -ForegroundColor Green
    } else {
        Write-Host "  .venv: 見つかりません（スキップ）" -ForegroundColor Gray
    }

    # --- Step 2: Delete Whisper model cache ---
    Write-Host ""
    Write-Host "Step 2/3: Whisper モデルキャッシュを削除中..." -ForegroundColor Yellow

    $hfCachePaths = @(
        "$env:USERPROFILE\.cache\huggingface\hub",
        "$env:HF_HOME\hub"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

    $deleted = $false
    foreach ($cachePath in $hfCachePaths) {
        $modelDirs = Get-ChildItem $cachePath -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "models--Systran--faster-whisper-*" -or $_.Name -like "models--mlx-community--whisper-*" }
        foreach ($dir in $modelDirs) {
            Remove-Item $dir.FullName -Recurse -Force
            Write-Host "  削除: $($dir.Name)" -ForegroundColor Green
            $deleted = $true
        }
    }
    if (-not $deleted) {
        Write-Host "  キャッシュが見つかりません（スキップ）" -ForegroundColor Gray
    }

    # --- Step 3: Remove Ollama model ---
    Write-Host ""
    Write-Host "Step 3/3: Ollama モデルを削除中..." -ForegroundColor Yellow
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        $ollamaList = ollama list 2>&1
        if ($ollamaList -match "qwen3:4b-q4_K_M") {
            ollama rm qwen3:4b-q4_K_M 2>&1 | Out-Null
            Write-Host "  qwen3:4b-q4_K_M: 削除完了" -ForegroundColor Green
        } else {
            Write-Host "  qwen3:4b-q4_K_M: 見つかりません（スキップ）" -ForegroundColor Gray
        }
    } else {
        Write-Host "  Ollama が見つかりません（スキップ）" -ForegroundColor Gray
    }

    # --- Optional: Uninstall winget packages ---
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  インストール済みツールの削除（任意）" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Echonote のセットアップ時にインストールしたツールを削除できます。" -ForegroundColor White
    Write-Host "他のアプリで使用している場合は N を選んでください。" -ForegroundColor Gray
    Write-Host ""

    $packages = @(
        @{ Id = "Ollama.Ollama";      Name = "Ollama（AI 実行環境）" },
        @{ Id = "Python.Python.3.12"; Name = "Python 3.12" },
        @{ Id = "Gyan.FFmpeg";        Name = "FFmpeg（音声変換ツール）" },
        @{ Id = "Git.Git";            Name = "Git" }
    )

    $toUninstall = @()
    foreach ($pkg in $packages) {
        Write-Host "  $($pkg.Name) を削除しますか？ [y/N]" -ForegroundColor Yellow -NoNewline
        $ans = Read-Host " "
        if ($ans -match "^[yY]$") {
            $toUninstall += $pkg
        }
    }

    if ($toUninstall.Count -gt 0) {
        Write-Host ""
        Write-Host "ツールを削除中..." -ForegroundColor Yellow
        foreach ($pkg in $toUninstall) {
            Write-Host "  $($pkg.Name)..." -ForegroundColor Cyan
            winget uninstall --id $pkg.Id --silent 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  $($pkg.Name): 削除完了" -ForegroundColor Green
            } else {
                Write-Host "  $($pkg.Name): 削除できませんでした（手動で削除してください）" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "  ツールの削除はスキップしました。" -ForegroundColor Gray
    }

    # --- Done ---
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  アンインストール完了" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Echonote フォルダ自体はそのまま残っています。" -ForegroundColor White
    Write-Host "  不要であれば手動で削除してください。" -ForegroundColor Gray

} catch {
    Write-Host ""
    Write-Host "エラーが発生しました:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host ""
Read-Host "Enter キーで閉じる"
