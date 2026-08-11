$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvDir = Join-Path $ScriptDir ".python_env"
$PythonUrl = "https://github.com/indygreg/python-build-standalone/releases/download/20240224/cpython-3.12.2+20240224-x86_64-pc-windows-msvc-shared-install_only.tar.gz"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  3X UI Deployment Manager Web UI Launcher  " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$PythonBin = ""

if (Test-Path (Join-Path $EnvDir "python.exe")) {
    $PythonBin = Join-Path $EnvDir "python.exe"
} else {
    $hasSysPython = $false
    try {
        $res = & python -c "import sys; sys.exit(0)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonBin = "python"
            $hasSysPython = $true
        }
    } catch {}

    if (-not $hasSysPython) {
        try {
            $res = & python3 -c "import sys; sys.exit(0)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonBin = "python3"
                $hasSysPython = $true
            }
        } catch {}
    }

    if (-not $hasSysPython) {
        Write-Host "[..] Portable Python not found. Downloading isolated runtime..." -ForegroundColor Yellow
        $TarGz = Join-Path $ScriptDir "python.tar.gz"
        Invoke-WebRequest -Uri $PythonUrl -OutFile $TarGz
        tar -xzf $TarGz -C $ScriptDir
        $ExtractedPython = Join-Path $ScriptDir "python"
        if (Test-Path $ExtractedPython) {
            Move-Item -Path $ExtractedPython -Destination $EnvDir -Force
        }
        Remove-Item -Path $TarGz -ErrorAction SilentlyContinue
        $PythonBin = Join-Path $EnvDir "python.exe"
        Write-Host "[OK] Portable Python installed into $EnvDir" -ForegroundColor Green
    }
}

Write-Host "[OK] Starting local Web UI application..." -ForegroundColor Green
$env:XUI_CLI_EXT = ".ps1"
& $PythonBin (Join-Path $ScriptDir "main.py")
