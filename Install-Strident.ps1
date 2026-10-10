$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 (64-bit) with the Windows py launcher, then run this installer again.' }
& py -3.12 -c 'import sys; print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required for this tested package.' }
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & py -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $pythonPath -c 'import sys; assert sys.version_info[:2] == (3, 12), "Recreate this package virtual environment with Python 3.12"'
if ($LASTEXITCODE -ne 0) { throw 'This virtual environment uses an incompatible Python version.' }
& $pythonPath -m pip install --requirement (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $pythonPath -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency compatibility check failed.' }
Push-Location $PSScriptRoot
try {
    & $pythonPath (Join-Path $PSScriptRoot 'verify_app.py')
    if ($LASTEXITCODE -ne 0) { throw 'Verification failed. Do not replace the existing installation.' }
} finally { Pop-Location }
& (Join-Path $PSScriptRoot 'Create-Desktop-Shortcut.ps1') -StridentFolder $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'The app is installed, but shortcut creation failed. Run Create-Desktop-Shortcut.cmd to retry.' }
Write-Host 'Strident installation verified.'
Write-Host 'Launch with the Strident.AI desktop shortcut or Launch-Strident.cmd. Read README.md for setup.'
