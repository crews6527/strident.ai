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

if ([string]::IsNullOrWhiteSpace($StridentFolder)) { $StridentFolder = $PSScriptRoot }
$root = (Resolve-Path -LiteralPath $StridentFolder -ErrorAction Stop).ProviderPath
if (-not (Test-StridentInstallation $root)) {
    throw "Incomplete Strident installation at '$root'. Run Install-Strident.cmd from that folder first."
}
$commandInterpreter = $env:ComSpec
if ([string]::IsNullOrWhiteSpace($commandInterpreter) -or
    -not (Test-Path -LiteralPath $commandInterpreter -PathType Leaf)) {
    throw 'Windows command interpreter was not found in ComSpec.'
}
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
if ([string]::IsNullOrWhiteSpace($desktop) -or
    -not (Test-Path -LiteralPath $desktop -PathType Container)) {
    throw 'The current user desktop folder could not be found.'
}

# Windows shortcuts use ICO files or executable icon resources, not PNG files.
$candidates = @(
    (Join-Path $root 'assets\app.ico'),
    (Join-Path $root 'assets\agent.ico')
)
$appIcon = $commandInterpreter + ',0'
foreach ($iconPath in $candidates) {
    if (Test-Path -LiteralPath $iconPath -PathType Leaf) {
        $appIcon = $iconPath + ',0'
        break
    }
}

$shortcutPath = Join-Path $desktop 'Strident.AI.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $commandInterpreter
$shortcut.Arguments = '/d /s /c ""' + (Join-Path $root 'Launch-Strident.cmd') + '""'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = $appIcon
$shortcut.Description = 'Launch Strident.AI'
$shortcut.WindowStyle = 1
$shortcut.Save()
if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
    throw "Shortcut was not saved at '$shortcutPath'."
}
Write-Host "Created $shortcutPath"
Write-Host "Installation: $root"
