@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "BACKUP_DIR=%SCRIPT_DIR%backup"
set "WORKING_DIR=%SCRIPT_DIR%working"
set "COMPOSE_FILE=%WORKING_DIR%\docker-compose\docker-compose.yml"

if not exist "%BACKUP_DIR%" (
  echo [ERROR] Backup directory "%BACKUP_DIR%" does not exist. 1>&2
  exit /b 1
)

xcopy "%BACKUP_DIR%\*" "%WORKING_DIR%\" /e /i /q /y >nul

if exist "%COMPOSE_FILE%" (
  docker compose -f "%COMPOSE_FILE%" --project-directory "%SCRIPT_DIR:~0,-1%" up -d
  if errorlevel 1 exit /b !errorlevel!
) else (
  echo [WARNING] docker-compose.yml not found at %COMPOSE_FILE%. Service was not restarted. 1>&2
)

echo Rollback completed successfully.
endlocal
