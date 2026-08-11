param([string]$BackupDir)

$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($BackupDir)) {
    $BackupDir = Join-Path $ScriptDir "backup"
}

if (Test-Path -LiteralPath $BackupDir) {
    Remove-Item -LiteralPath $BackupDir -Recurse -Force
}
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

$items = @('3x-ui', 'docker-compose', 'nginx-decoy', 'caddy')
foreach ($item in $items) {
    $src = Join-Path $ScriptDir "working\$item"
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination $BackupDir -Recurse -Force
    }
}
