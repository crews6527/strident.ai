# Explicit repair of THIS folder only. No process killing or security exclusions.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$environment = Join-Path $root '.venv'
$backup = Join-Path $root ('.venv-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-ffff'))
$renamed = $false
$created = $false
try {
    # Refuse repair while this app is running. Do not stop Python/Ollama/other apps.
    $owned = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and
        (($_.CommandLine.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
         ($_.ExecutablePath -and $_.ExecutablePath.StartsWith(($root + '\'), [StringComparison]::OrdinalIgnoreCase))) -and
        $_.CommandLine -match '(guard_strident|main|live_preview|verify_idle)\.py'
    }
    if ($owned) { throw 'Close Strident and its preview in this folder before recovery. No process was stopped.' }
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python 3.12 with the Windows py launcher is required.' }
    & py -3.12 -I -c 'import sys; assert sys.version_info[:2] == (3,12)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is unavailable.' }
    # Validate the package BEFORE renaming the previous environment.
    & py -3.12 -I (Join-Path $root 'guard_strident.py') --integrity
    if ($LASTEXITCODE -ne 0) { throw 'Package validation failed. Extract the recovery package into a separate folder.' }
    if (Test-Path -LiteralPath $environment) { Move-Item -LiteralPath $environment -Destination $backup; $renamed = $true }
    $created = $true
    & py -3.12 -I -m venv $environment
    if ($LASTEXITCODE -ne 0) { throw 'Could not create a clean environment.' }
    $python = Join-Path $environment 'Scripts\python.exe'
    & $python -I -m pip --isolated install -r (Join-Path $root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed.' }
    & $python -I -m pip --isolated check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency compatibility check failed.' }
    & $python -I (Join-Path $root 'guard_strident.py') --check
    if ($LASTEXITCODE -ne 0) { throw 'Application preflight failed. See the startup log; personal configuration was preserved.' }
    Write-Host 'Recovery preflight passed. Open Launch-Strident.cmd in THIS folder.'
    Write-Host 'Settings, history, projects, Ollama and other apps were not reset.'
    if ($renamed) { Write-Host "Previous environment preserved: $backup" }
    Write-Host 'Real Windows launch and a completed generation task still require your device test.'
} catch {
    if ($created -and (Test-Path -LiteralPath $environment)) {
        # Preserve a failed repair for diagnostics instead of deleting it.
        Move-Item -LiteralPath $environment -Destination ($environment + '-failed-' + (Get-Date -Format 'yyyyMMdd-HHmmss-ffff'))
    }
    if ($renamed) { Move-Item -LiteralPath $backup -Destination $environment }
    Write-Error ('Recovery stopped: ' + $_.Exception.Message)
    exit 1
}
