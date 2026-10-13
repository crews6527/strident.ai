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

function Find-StridentInstallation {
    if (Test-StridentInstallation $PSScriptRoot) { return $PSScriptRoot }
    $downloads = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads'
    $explorer = $null
    try {
        $explorer = New-Object -ComObject Shell.Application
        $downloadsNamespace = $explorer.NameSpace('shell:Downloads')
        if ($null -ne $downloadsNamespace) { $downloads = $downloadsNamespace.Self.Path }
    } catch {
        # The standard Downloads folder is still usable without shell discovery.
    } finally {
        if ($null -ne $explorer) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($explorer) }
    }
    $candidates = @()
    if (Test-Path -LiteralPath $downloads -PathType Container) {
        foreach ($folder in Get-ChildItem -LiteralPath $downloads -Directory -ErrorAction SilentlyContinue) {
            foreach ($possible in @($folder.FullName, (Join-Path $folder.FullName 'STRIDENT_AI_RC2'), (Join-Path $folder.FullName 'STRIDENT_AI_RC2_CURBSENTRY'))) {
                if (Test-StridentInstallation $possible) { $candidates += $possible }
            }
        }
    }
    $candidates = @($candidates | Sort-Object -Unique)
    if ($candidates.Count -eq 1) { return $candidates[0] }

    Add-Type -AssemblyName System.Windows.Forms
    $picker = New-Object System.Windows.Forms.FolderBrowserDialog
    try {
        $picker.Description = 'Choose the installed Strident folder containing main.py and Launch-Strident.cmd.'
        $picker.ShowNewFolderButton = $false
        if (Test-Path -LiteralPath $downloads -PathType Container) { $picker.SelectedPath = $downloads }
        if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            throw 'No folder selected. No shortcuts created.'
        }
        return $picker.SelectedPath
    } finally { $picker.Dispose() }
}

function Save-StridentShortcut {
    param($Shell, [string]$Desktop, [string]$Name, [string]$Target,
          [string]$Arguments, [string]$WorkingFolder, [string]$Description, [string]$Icon)
    $linkPath = Join-Path $Desktop ($Name + '.lnk')
    $suffix = 2
    # Keep an unrelated existing shortcut. Re-running for this installation reuses its link.
    while (Test-Path -LiteralPath $linkPath) {
        $existing = $Shell.CreateShortcut($linkPath)
        try {
            $same = $existing.TargetPath -eq $Target -and
                    $existing.Arguments -eq $Arguments -and
                    $existing.WorkingDirectory -eq $WorkingFolder
        } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($existing) }
        if ($same) { break }
        $linkPath = Join-Path $Desktop ('{0} ({1}).lnk' -f $Name, $suffix)
        $suffix += 1
    }
    $link = $Shell.CreateShortcut($linkPath)
    try {
        $link.TargetPath = $Target
        $link.Arguments = $Arguments
        $link.WorkingDirectory = $WorkingFolder
        $link.Description = $Description
        $link.WindowStyle = 1
        $link.IconLocation = $Icon
        $link.Save()
    } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link) }
    if (-not (Test-Path -LiteralPath $linkPath -PathType Leaf)) { throw ('Shortcut was not saved: ' + $linkPath) }
    $saved = $Shell.CreateShortcut($linkPath)
    try {
        if ($saved.TargetPath -ne $Target -or $saved.Arguments -ne $Arguments -or $saved.WorkingDirectory -ne $WorkingFolder) {
            throw ('Shortcut verification failed: ' + $linkPath)
        }
    } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($saved) }
    Write-Host ('Ready: ' + $linkPath)
}

$shell = $null
try {
    if ([string]::IsNullOrWhiteSpace($StridentFolder)) { $StridentFolder = Find-StridentInstallation }
    if (-not (Test-StridentInstallation $StridentFolder)) {
        throw 'Select the installed Strident folder containing main.py, Launch-Strident.cmd and .venv. No shortcuts created.'
    }
    $root = (Resolve-Path -LiteralPath $StridentFolder).ProviderPath
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw 'Your Windows Desktop folder could not be located. No shortcuts created.'
    }
    $commandInterpreter = Join-Path ([Environment]::GetFolderPath('System')) 'cmd.exe'
    if (-not (Test-Path -LiteralPath $commandInterpreter -PathType Leaf)) { throw 'Windows Command Prompt was not found.' }
    $launcher = Join-Path $root 'Launch-Strident.cmd'
    $iconPath = Join-Path $root 'assets\agent.ico'
    $appIcon = $commandInterpreter + ',0'
    if (Test-Path -LiteralPath $iconPath -PathType Leaf) { $appIcon = $iconPath + ',0' }
    $shell = New-Object -ComObject WScript.Shell
    Write-Host ('Strident folder: ' + $root)
    $version = 'unknown'
    $versionFile = Join-Path $root 'pcs_agent\__init__.py'
    $versionText = Get-Content -LiteralPath $versionFile -Raw
    if ($versionText -match '__version__\s*=\s*"([0-9.]+)"') { $version = $Matches[1] }
    $shortcutName = 'Strident.AI ' + $version
    Save-StridentShortcut -Shell $shell -Desktop $desktop -Name $shortcutName `
        -Target $commandInterpreter -Arguments ('/D /C ""{0}""' -f $launcher) `
        -WorkingFolder $root -Description 'Launch Strident with its console window.' -Icon $appIcon
    Write-Host ('Double-click ' + $shortcutName + ' on your Desktop to launch this version.')
    Write-Host 'Keep the installed Strident folder in place. These shortcuts point to that folder.'
} catch {
    Write-Host ('STOPPED: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    if ($null -ne $shell) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
}
