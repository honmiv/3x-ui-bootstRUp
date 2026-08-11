@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_sources.ps1"
exit /b %errorlevel%
