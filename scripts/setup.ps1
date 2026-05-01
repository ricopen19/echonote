# Echonote Setup Script

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- 管理者権限がなければ自動で昇格して再起動 ---
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -ArgumentList ('-ExecutionPolicy Bypass -File "' + $PSCommandPath + '"') -Verb RunAs
    exit
}

# --- メイン処理 ---
try {

    $rootDir = Split-Path $PSScriptRoot -Parent
    Set-Location $rootDir
    Write-Host "作業ディレクトリ: $rootDir" -ForegroundColor Gray

    # --- Step 1: ツールのインストール ---
    Write-Host ""
    Write-Host "Step 1/4: 必要なツールをインストールしています..." -ForegroundColor Yellow

    $packages = @(
        @{ Id = "Python.Python.3.12"; Name = "Python 3.12" },
        @{ Id = "Gyan.FFmpeg";        Name = "ffmpeg" },
        @{ Id = "Ollama.Ollama";      Name = "Ollama" },
        @{ Id = "Git.Git";            Name = "Git" }
    )

    foreach ($pkg in $packages) {
        Write-Host "  [$($pkg.Name)] インストール中..." -ForegroundColor Cyan
        winget install --id $pkg.Id --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) {
            Write-Host "  [$($pkg.Name)] OK" -ForegroundColor Green
        } else {
            Write-Host "  [$($pkg.Name)] スキップ (インストール済みの可能性あり)" -ForegroundColor Yellow
        }
    }

    # --- Step 2: PATH を更新 ---
    Write-Host ""
    Write-Host "Step 2/4: PATH を更新しています..." -ForegroundColor Yellow

    $env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

    # ffmpeg が PATH に入っていない場合の補完
    $ffmpegCandidates = @("C:\Program Files\ffmpeg\bin", "C:\ffmpeg\bin")
    foreach ($p in $ffmpegCandidates) {
        if ((Test-Path $p) -and ($env:PATH -notlike "*ffmpeg*")) {
            $mp = [Environment]::GetEnvironmentVariable("Path", "Machine")
            [Environment]::SetEnvironmentVariable("Path", $mp + ";" + $p, "Machine")
            $env:PATH += ";" + $p
            Write-Host "  ffmpeg PATH 追加: $p" -ForegroundColor Green
        }
    }

    foreach ($cmd in @("python", "ffmpeg", "ollama")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            Write-Host "  $cmd : OK" -ForegroundColor Green
        } else {
            Write-Host "  $cmd : 見つかりません (再起動後に使えるようになります)" -ForegroundColor Yellow
        }
    }

    # --- Step 3: uv と依存パッケージ ---
    Write-Host ""
    Write-Host "Step 3/4: Echonote の依存パッケージをインストールしています..." -ForegroundColor Yellow

    python -m pip install uv --quiet
    Write-Host "  uv : OK" -ForegroundColor Green

    uv sync
    Write-Host "  依存パッケージ : OK" -ForegroundColor Green

    # --- Step 4: Ollama モデルのダウンロード ---
    Write-Host ""
    Write-Host "Step 4/4: LLM モデルのダウンロード" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  文字起こし結果を整形する AI モデル (約 2.5GB) をダウンロードします。" -ForegroundColor White
    Write-Host "  ダウンロードには数分から十数分かかります。" -ForegroundColor Gray
    Write-Host ""
    $answer = Read-Host "  ダウンロードしますか？ [y/N]"
    if ($answer -match "^[yY]$") {
        Write-Host "  ダウンロード中..." -ForegroundColor Cyan
        ollama pull qwen3:4b-q4_K_M
        Write-Host "  モデル : OK" -ForegroundColor Green
    } else {
        Write-Host "  スキップしました。後で 'ollama pull qwen3:4b-q4_K_M' を実行してください。" -ForegroundColor Yellow
    }

    # --- 完了 ---
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host " セットアップ完了！" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "PC を再起動してから start.bat をダブルクリックして起動してください。" -ForegroundColor White

} catch {
    Write-Host ""
    Write-Host "エラーが発生しました:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host ""
Read-Host "Enter キーを押すと終了します"
