# Echonote Setup Script

# --- Elevate to admin if needed ---
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -ArgumentList ('-ExecutionPolicy Bypass -File "' + $PSCommandPath + '"') -Verb RunAs
    exit
}

try {

    $rootDir = Split-Path $PSScriptRoot -Parent
    Set-Location $rootDir
    Write-Host "Working directory: $rootDir" -ForegroundColor Gray

    # --- Step 1: Install tools ---
    Write-Host ""
    Write-Host "Step 1/4: Installing tools..." -ForegroundColor Yellow

    $packages = @(
        @{ Id = "Python.Python.3.12"; Name = "Python 3.12" },
        @{ Id = "Gyan.FFmpeg";        Name = "ffmpeg" },
        @{ Id = "Ollama.Ollama";      Name = "Ollama" },
        @{ Id = "Git.Git";            Name = "Git" }
    )

    foreach ($pkg in $packages) {
        Write-Host "  Installing $($pkg.Name)..." -ForegroundColor Cyan
        winget install --id $pkg.Id --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) {
            Write-Host "  $($pkg.Name): OK" -ForegroundColor Green
        } else {
            Write-Host "  $($pkg.Name): skipped (may already be installed)" -ForegroundColor Yellow
        }
    }

    # --- Step 2: Update PATH ---
    Write-Host ""
    Write-Host "Step 2/4: Updating PATH..." -ForegroundColor Yellow

    $env:PATH = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

    foreach ($p in @("C:\Program Files\ffmpeg\bin", "C:\ffmpeg\bin")) {
        if ((Test-Path $p) -and ($env:PATH -notlike "*ffmpeg*")) {
            $mp = [Environment]::GetEnvironmentVariable("Path", "Machine")
            [Environment]::SetEnvironmentVariable("Path", $mp + ";" + $p, "Machine")
            $env:PATH += ";" + $p
            Write-Host "  ffmpeg PATH added: $p" -ForegroundColor Green
        }
    }

    foreach ($cmd in @("python", "ffmpeg", "ollama")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            Write-Host "  $cmd : OK" -ForegroundColor Green
        } else {
            Write-Host "  $cmd : not found (restart PC after setup)" -ForegroundColor Yellow
        }
    }

    # --- Step 3: Install Python dependencies ---
    Write-Host ""
    Write-Host "Step 3/4: Installing Echonote dependencies..." -ForegroundColor Yellow

    python -m pip install uv --quiet
    Write-Host "  uv: OK" -ForegroundColor Green

    uv sync --extra diarization --extra moonshine
    Write-Host "  packages: OK" -ForegroundColor Green

    # sherpa-onnx がバンドルする古い ORT を Python onnxruntime パッケージの新しい DLL で
    # 上書きする。これにより Moonshine モデルが要求する ORT API v24 が使えるようになる。
    $sherpaDir = (uv run python -c "import sherpa_onnx, os; print(os.path.dirname(sherpa_onnx.__file__))").Trim()
    $ortCapiDir = (uv run python -c "import onnxruntime, os; print(os.path.join(os.path.dirname(onnxruntime.__file__), 'capi'))").Trim()
    $systemOrtDll = Join-Path $ortCapiDir "onnxruntime.dll"
    $sherpaOrtDll = Get-ChildItem -Path $sherpaDir -Filter "onnxruntime.dll" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($sherpaOrtDll -and (Test-Path $systemOrtDll)) {
        Copy-Item $systemOrtDll $sherpaOrtDll -Force
        Write-Host "  ORT DLL patched for Moonshine: OK" -ForegroundColor Green
    } else {
        Write-Host "  ORT DLL patch skipped (sherpa=$sherpaDir, ort=$systemOrtDll)" -ForegroundColor Yellow
    }

    # --- Step 4: Download Ollama model ---
    Write-Host ""
    Write-Host "Step 4/5: Download AI model (approx. 800MB)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  This downloads the AI model needed for summarization." -ForegroundColor White
    Write-Host "  It may take several minutes depending on your connection." -ForegroundColor Gray
    Write-Host ""
    $answer = Read-Host "  Download now? [y/N]"
    if ($answer -match "^[yY]$") {
        Write-Host "  Downloading..." -ForegroundColor Cyan
        ollama pull hf.co/LiquidAI/LFM2.5-1.2B-JP-202606-GGUF:Q4_K_M
        Write-Host "  model: OK" -ForegroundColor Green
    } else {
        Write-Host "  Skipped. Run 'ollama pull hf.co/LiquidAI/LFM2.5-1.2B-JP-202606-GGUF:Q4_K_M' later." -ForegroundColor Yellow
    }

    # --- Step 5: Download Moonshine model ---
    Write-Host ""
    Write-Host "Step 5/5: Download Moonshine speech recognition model (approx. 200MB)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Moonshine is a lightweight transcription engine." -ForegroundColor White
    Write-Host "  Recommended for low-spec PCs (faster than Whisper)." -ForegroundColor White
    Write-Host "  It may take several minutes depending on your connection." -ForegroundColor Gray
    Write-Host ""
    $answer = Read-Host "  Download now? [y/N]"
    if ($answer -match "^[yY]$") {
        Write-Host "  Downloading..." -ForegroundColor Cyan
        uv run python -c "from echonote.transcriber import _ensure_moonshine_assets; _ensure_moonshine_assets()"
        Write-Host "  Moonshine model: OK" -ForegroundColor Green
    } else {
        Write-Host "  Skipped. The model will be downloaded automatically on first use." -ForegroundColor Yellow
    }

    # --- Done ---
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "  Setup complete!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Please restart your PC, then double-click start.bat to launch Echonote." -ForegroundColor White

} catch {
    Write-Host ""
    Write-Host "Error:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"
