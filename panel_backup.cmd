@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "BACKUP_DIR=%~1"
if "%BACKUP_DIR%"=="" set "BACKUP_DIR=%SCRIPT_DIR%backup"

if exist "%BACKUP_DIR%" (
  rd /s /q "%BACKUP_DIR%"
)
mkdir "%BACKUP_DIR%" 2>nul

if exist "%SCRIPT_DIR%working\3x-ui" xcopy /e /i /q /y "%SCRIPT_DIR%working\3x-ui" "%BACKUP_DIR%\3x-ui" >nul
if exist "%SCRIPT_DIR%working\docker-compose" xcopy /e /i /q /y "%SCRIPT_DIR%working\docker-compose" "%BACKUP_DIR%\docker-compose" >nul
if exist "%SCRIPT_DIR%working\nginx-decoy" xcopy /e /i /q /y "%SCRIPT_DIR%working\nginx-decoy" "%BACKUP_DIR%\nginx-decoy" >nul
if exist "%SCRIPT_DIR%working\caddy" xcopy /e /i /q /y "%SCRIPT_DIR%working\caddy" "%BACKUP_DIR%\caddy" >nul

endlocal
