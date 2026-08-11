param([string]$Version)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($Version)) {
    Write-Host "Usage: panel_update.ps1 <version>" -ForegroundColor Red
    exit 1
}

$ScriptDir = $PSScriptRoot
$ComposeFile = Join-Path $ScriptDir "working\docker-compose\docker-compose.yml"

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    Write-Host "File not found: $ComposeFile" -ForegroundColor Red
    exit 1
}

& (Join-Path $ScriptDir "panel_backup.ps1")

$lines = [System.IO.File]::ReadAllLines($ComposeFile)
$out = New-Object System.Collections.Generic.List[string]
$in3xui = $false
$indent = -1

foreach ($line in $lines) {
    if ($line -match '^\s*3xui:\s*$') {
        $in3xui = $true
        $indent = $line.Length - $line.TrimStart().Length
        $out.Add($line)
        continue
    }

    if ($in3xui -and $line -match '^\s*\S') {
        $curIndent = $line.Length - $line.TrimStart().Length
        if ($curIndent -le $indent) {
            $in3xui = $false
        }
    }

    if ($in3xui -and $line -match '^\s*image:\s*') {
        $line = [regex]::Replace($line, 'ghcr\.io/mhsanaei/3x-ui:[^\s''"]*', "ghcr.io/mhsanaei/3x-ui:$Version")
    }

    $out.Add($line)
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($ComposeFile, $out.ToArray(), $utf8NoBom)

docker compose -f $ComposeFile --project-directory $ScriptDir up -d 3xui
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
