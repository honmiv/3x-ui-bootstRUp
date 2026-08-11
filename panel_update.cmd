@echo off
setlocal

set "VERSION=%~1"
if "%VERSION%"=="" (
  echo Usage: %~nx0 ^<version^>
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0panel_update.ps1" "%VERSION%"
exit /b %errorlevel%
