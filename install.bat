@echo off
setlocal enabledelayedexpansion

set "ENV_DIR=%~dp0.python_env"
set "PYTHON_URL=https://github.com/indygreg/python-build-standalone/releases/download/20240224/cpython-3.12.2+20240224-x86_64-pc-windows-msvc-shared-install_only.tar.gz"

echo =========================================
echo   3x-ui-bootstRUp Local Web UI Launcher 
echo =========================================

if exist "%ENV_DIR%\python.exe" (
    set "PYTHON_BIN=%ENV_DIR%\python.exe"
) else (
    python -c "import sys; sys.exit(0)" >nul 2>nul
    if !errorlevel! equ 0 (
        set "PYTHON_BIN=python"
    ) else (
        python3 -c "import sys; sys.exit(0)" >nul 2>nul
        if !errorlevel! equ 0 (
            set "PYTHON_BIN=python3"
        ) else (
            echo [..] Portable Python not found. Downloading isolated runtime...
            powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%~dp0python.tar.gz'"
            powershell -Command "tar -xzf '%~dp0python.tar.gz' -C '%~dp0'"
            if exist "%~dp0python" (
                move "%~dp0python" "%ENV_DIR%" >nul
            )
            del "%~dp0python.tar.gz" >nul 2>nul
            set "PYTHON_BIN=%ENV_DIR%\python.exe"
            echo [OK] Portable Python installed into %ENV_DIR%
        )
    )
)

echo [OK] Starting local Web UI application...
"%PYTHON_BIN%" "%~dp0main.py"
pause
