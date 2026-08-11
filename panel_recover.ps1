$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$BackupDir = Join-Path $ScriptDir "backup"
$WorkingDir = Join-Path $ScriptDir "working"
$ComposeFile = Join-Path $WorkingDir "docker-compose\docker-compose.yml"

if (-not (Test-Path -LiteralPath $BackupDir)) {
    Write-Host "[ERROR] Backup directory '$BackupDir' does not exist." -ForegroundColor Red
    exit 1
}

Copy-Item -Path (Join-Path $BackupDir '*') -Destination $WorkingDir -Recurse -Force

if (Test-Path -LiteralPath $ComposeFile) {
    docker compose -f $ComposeFile --project-directory $ScriptDir up -d
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "[WARNING] docker-compose.yml not found at $ComposeFile. Service was not restarted." -ForegroundColor Yellow
}

Write-Host "Rollback completed successfully." -ForegroundColor Green
