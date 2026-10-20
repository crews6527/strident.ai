param([string]$StridentFolder)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-StridentInstallation([string]$Folder) {
    if ([string]::IsNullOrWhiteSpace($Folder)) { return $false }
    foreach ($relative in @('main.py', 'Launch-Strident.cmd', 'pcs_agent\ui.py', '.venv\Scripts\python.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Folder $relative) -PathType Leaf)) { return $false }
    }
    return $true
}

# Prefer a dedicated .ico; fall back to face.png so the shortcut is not stuck on an old icon.
$candidates = @(
    (Join-Path $root 'assets\app.ico'),
    (Join-Path $root 'assets\agent.ico'),
    (Join-Path $root 'assets\face.png')
)
$appIcon = $commandInterpreter + ',0'
foreach ($iconPath in $candidates) {
    if (Test-Path -LiteralPath $iconPath -PathType Leaf) {
        $appIcon = $iconPath + ',0'
        break
    }
}
