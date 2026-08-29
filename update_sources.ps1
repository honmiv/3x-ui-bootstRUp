$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$Repo = if ($env:REPO) { $env:REPO } else { 'honmiv/3x-ui-bootstRUp' }
$Branch = if ($env:BRANCH) { $env:BRANCH } else { 'master' }

$TargetDir = $env:TARGET_DIR
if (-not $TargetDir) { $TargetDir = $env:INSTALL_DIR }
if (-not $TargetDir) { $TargetDir = $ScriptDir }

$ArchiveUrl = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"

$TmpDir = Join-Path $env:TEMP ("3x-ui-update-" + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $TmpDir | Out-Null

try {
    if ((Test-Path (Join-Path $TargetDir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "[..] Detected Git repository. Updating via git fetch & reset..."
        Push-Location $TargetDir
        try {
            git fetch origin $Branch
            git reset --hard "origin/$Branch"
            Write-Host "[OK] Git repository reset to origin/$Branch."
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "[..] Downloading latest sources from $ArchiveUrl..."
        Invoke-WebRequest -Uri $ArchiveUrl -OutFile (Join-Path $TmpDir "src.zip") -UseBasicParsing

        Expand-Archive -Path (Join-Path $TmpDir "src.zip") -DestinationPath $TmpDir

        $src = Get-ChildItem -LiteralPath $TmpDir -Directory | Where-Object { $_.Name -ne '__MACOSX' } | Select-Object -First 1
        if (-not $src) {
            Write-Host "[ERROR] Downloaded archive is empty or invalid." -ForegroundColor Red
            exit 1
        }

        Write-Host "[..] Cleaning working directory at $TargetDir..."
        Write-Host "[..] Preserving 'backups_panel'/'backups_sub_server' folders, 'setup_backup.yml' file, 'servers.json', and '.git' repository."

        $preserve = @('backups_panel', 'backups_sub_server', 'backup', 'setup_backup.yml', 'setup_backup.yaml', 'servers.json', '.git', 'panel')
        Get-ChildItem -LiteralPath $TargetDir -Force | ForEach-Object {
            if ($preserve -contains $_.Name) {
                Write-Host "[KEEP] $($_.Name)"
            } else {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
            }
        }

        Write-Host "[..] Extracting updated files..."
        Get-ChildItem -LiteralPath $src.FullName -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $TargetDir -Recurse -Force
        }
    }

    Write-Host "[OK] Project files updated successfully."

    $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine -like '*main.py*'
    })
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $startScript = Join-Path $TargetDir "start_3x_ui_deployment_manager.ps1"
    if (Test-Path -LiteralPath $startScript) {
        Write-Host "[..] Starting local Web UI application..."
        & $startScript
    }
}
finally {
    Remove-Item -LiteralPath $TmpDir -Recurse -Force -ErrorAction SilentlyContinue
}
