<#
.SYNOPSIS
    Applies a WYSIWYG loose-file patch to an installed copy.

.DESCRIPTION
    Backs up every file it replaces, copies the payload (version.json last),
    verifies each file against the SHA-256 in patch.json, and rolls the whole
    patch back if anything does not match.

    Run it from the patch folder - it expects patch.json and files\ next to it.

.PARAMETER InstallDir
    Install folder. Defaults to the registry's InstallLocation, then
    C:\FYRTOOLS\WYSIWYG.

.PARAMETER NoStart
    Do not restart WYSIWYG.exe afterwards.

.PARAMETER Yes
    Skip the confirmation prompt.

.PARAMETER DryRun
    Check everything (install folder, versions, payload checksums) and change
    nothing.

.PARAMETER SkipStop
    Accepted for compatibility. The app is no longer killed before copying: a
    fresh instance replaces the running one, so this does nothing.

.PARAMETER PatchDir
    Folder holding patch.json and files\. Defaults to the folder this script is
    in, which is how a patch ships.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = '',
    [switch]$NoStart,
    [switch]$Yes,
    [switch]$DryRun,
    [switch]$SkipStop,
    [string]$PatchDir = ''
)

$ErrorActionPreference = 'Stop'

# Every run leaves a line-by-line trace. The app-triggered updater closes its
# console as soon as it ends, so without this a failure is invisible.
$LogPath = Join-Path $env:TEMP 'wysiwyg_patch_apply.log'
function Write-PatchLog([string]$message) {
    try {
        $line = "{0} [{1}] {2}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $PID, $message
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    } catch { }
    Write-Host $message
}

trap {
    Write-PatchLog ("FATAL: " + $_.Exception.Message)
    exit 1
}

if ([string]::IsNullOrWhiteSpace($PatchDir)) { $PatchDir = $PSScriptRoot }
try {
    $PatchDir = (Resolve-Path -LiteralPath $PatchDir -ErrorAction Stop).ProviderPath
} catch {
    throw "Patch folder not found: $PatchDir"
}
$PatchManifestPath = Join-Path $PatchDir 'patch.json'
$PayloadDir = Join-Path $PatchDir 'files'
$InnoAppId = '{C349C35F-55AA-466D-B029-6D39D55C0E28}_is1'

function Format-Version($v) {
    return '{0}.{1}.{2}.{3}' -f ([int]$v.major), ([int]$v.minor), ([int]$v.patch), ([int]$v.build)
}

function Read-Version([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $raw = Get-Content -LiteralPath $path -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    $v = $raw | ConvertFrom-Json
    return [pscustomobject]@{
        major = [int]$v.major
        minor = [int]$v.minor
        patch = [int]$v.patch
        build = [int]$v.build
    }
}

function Compare-Version($a, $b) {
    foreach ($key in @('major', 'minor', 'patch', 'build')) {
        if ([int]$a.$key -lt [int]$b.$key) { return -1 }
        if ([int]$a.$key -gt [int]$b.$key) { return 1 }
    }
    return 0
}

function Resolve-InstallDir {
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$InnoAppId",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\$InnoAppId"
    )
    foreach ($key in $keys) {
        try {
            $loc = (Get-ItemProperty -Path $key -Name InstallLocation -ErrorAction Stop).InstallLocation
            if ($loc) {
                $loc = $loc.TrimEnd('\')
                if (Test-Path -LiteralPath (Join-Path $loc 'WYSIWYG.exe')) { return $loc }
            }
        } catch { }
    }
    if (Test-Path -LiteralPath 'C:\FYRTOOLS\WYSIWYG\WYSIWYG.exe') { return 'C:\FYRTOOLS\WYSIWYG' }
    return ''
}

function Test-CanWrite([string]$dir) {
    $probe = Join-Path $dir ('.patch-probe-' + [guid]::NewGuid().ToString('N'))
    try {
        [System.IO.File]::WriteAllText($probe, 'probe')
        Remove-Item -LiteralPath $probe -Force
        return $true
    } catch {
        return $false
    }
}

# The running app is not killed here on purpose. WYSIWYG.exe already terminates
# an older instance when it starts ("Found old instance ... Terminating"), so the
# updater just starts a fresh one after the files are verified. That also means
# this script is never the thing that closes its own parent mid-copy.

# --- Validate the patch itself ---------------------------------------------
if (-not (Test-Path -LiteralPath $PatchManifestPath)) {
    throw "patch.json not found next to apply_patch.ps1 ($PatchDir)."
}
if (-not (Test-Path -LiteralPath $PayloadDir)) {
    throw "files\ not found next to apply_patch.ps1 ($PatchDir)."
}

$manifest = Get-Content -LiteralPath $PatchManifestPath -Raw | ConvertFrom-Json
$patchVersion = $manifest.version
$entries = @($manifest.files)
if ($entries.Count -eq 0) { throw 'patch.json lists no files.' }

foreach ($entry in $entries) {
    $rel = ([string]$entry.path).Replace('/', '\')
    if ([string]::IsNullOrWhiteSpace($rel) -or $rel -match '(^[\\/])' -or $rel -match '\.\.') {
        throw "Unsafe path in patch.json: $($entry.path)"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PayloadDir $rel) -PathType Leaf)) {
        throw "patch.json lists $rel but files\$rel is missing."
    }
}

# --- Find the install -------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($InstallDir)) { $InstallDir = Resolve-InstallDir }
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    throw 'WYSIWYG is not installed in the registry or C:\FYRTOOLS\WYSIWYG. Pass -InstallDir "D:\path\to\WYSIWYG".'
}
$InstallDir = $InstallDir.TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $InstallDir 'WYSIWYG.exe'))) {
    throw "No WYSIWYG.exe in $InstallDir - pass -InstallDir if the app lives elsewhere."
}

$installed = Read-Version (Join-Path $InstallDir 'version.json')
if ($null -eq $installed) {
    Write-Host 'Warning: no readable version.json in the install folder.' -ForegroundColor Yellow
}

if ($null -ne $installed -and (Compare-Version $patchVersion $installed) -le 0) {
    Write-Host ''
    Write-Host ("Already at " + (Format-Version $installed) + " - this patch is " + (Format-Version $patchVersion) + '.') -ForegroundColor Green
    Write-Host 'Nothing to do.'
    exit 0
}

# --- Dry run stops here -----------------------------------------------------
if ($DryRun) {
    Write-Host ''
    Write-Host ("Dry run: " + (Format-Version $patchVersion) + " -> $InstallDir") -ForegroundColor Cyan
    if ($null -ne $installed) { Write-Host ("  current : " + (Format-Version $installed)) }
    Write-Host ("  files   : " + $entries.Count)
    $badPayload = @()
    foreach ($entry in $entries) {
        $rel = ([string]$entry.path).Replace('/', '\')
        $src = Join-Path $PayloadDir $rel
        $actual = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$entry.sha256).ToLowerInvariant()) { $badPayload += $rel }
    }
    if ($badPayload.Count -gt 0) {
        throw ('Payload does not match patch.json: ' + ($badPayload -join ', '))
    }
    Write-Host '  payload : verified'
    Write-Host 'Nothing was changed.'
    exit 0
}

# --- Admin, only when the folder really is not writable ---------------------
# Captured before anything is copied: a patch never carries Python, so a running
# app can serve the new loose files on the next page load. Starting a second
# instance would just open a second browser tab (17 Nov 2026).
$appWasRunning = @(Get-Process -Name 'WYSIWYG' -ErrorAction SilentlyContinue).Count -gt 0
if (-not (Test-CanWrite $InstallDir)) {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-PatchLog "needs elevation for $InstallDir"
        Write-Host "Administrator rights are needed to write to $InstallDir - asking for them..." -ForegroundColor Yellow
        $argLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -PatchDir "{1}" -InstallDir "{2}"' -f $PSCommandPath, $PatchDir, $InstallDir
        if ($NoStart) { $argLine += ' -NoStart' }
        if ($Yes) { $argLine += ' -Yes' }
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argLine -Wait
        exit 0
    }
    throw "Cannot write to $InstallDir even as administrator."
}

# --- Confirm ----------------------------------------------------------------
$installedText = if ($null -ne $installed) { Format-Version $installed } else { 'unknown' }
Write-PatchLog ("start: patch {0}, install {1}, current {2}" -f (Format-Version $patchVersion), $InstallDir, $installedText)
Write-Host ''
Write-Host '  WYSIWYG patch ' -NoNewline
Write-Host (Format-Version $patchVersion) -ForegroundColor Cyan
if ($manifest.note) { Write-Host "  $($manifest.note)" }
Write-Host "  install : $InstallDir"
if ($null -ne $installed) { Write-Host ("  current : " + (Format-Version $installed)) }
Write-Host ("  files   : " + $entries.Count)
foreach ($entry in $entries) { Write-Host ("            " + $entry.path) }
Write-Host ''

if (-not $Yes) {
    $answer = Read-Host 'Apply now? [Y/n]'
    if ($answer -and $answer.Trim().ToLowerInvariant() -notin @('y', 'yes')) {
        Write-Host 'Cancelled - nothing was changed.'
        exit 1
    }
}

# --- Backup -----------------------------------------------------------------
$parent = Split-Path -Parent $InstallDir
$backupDir = Join-Path $parent 'wysiwyg.patch-backup'
if (Test-Path -LiteralPath $backupDir) {
    Remove-Item -LiteralPath $backupDir -Recurse -Force
}
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Write-PatchLog ("backup: " + $backupDir)

$newFiles = New-Object System.Collections.Generic.List[string]
foreach ($entry in $entries) {
    $rel = ([string]$entry.path).Replace('/', '\')
    $installedFile = Join-Path $InstallDir $rel
    if (Test-Path -LiteralPath $installedFile) {
        $backupFile = Join-Path $backupDir $rel
        $backupParent = Split-Path -Parent $backupFile
        if (-not (Test-Path -LiteralPath $backupParent)) {
            New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
        }
        Copy-Item -LiteralPath $installedFile -Destination $backupFile -Force
    } else {
        $newFiles.Add($rel)
    }
}
$replacedText = if ($null -ne $installed) { Format-Version $installed } else { 'unknown' }
$info = @(
    'WYSIWYG patch backup',
    ("replaced version : " + $replacedText),
    ("patch version    : " + (Format-Version $patchVersion)),
    ("created          : " + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')),
    '',
    'To roll back: close WYSIWYG, copy this folder''s contents over the install',
    'folder, then start WYSIWYG again. Files that did not exist before are listed',
    'as new-files.txt and must be deleted by hand.'
)
$info | Set-Content -LiteralPath (Join-Path $backupDir 'patch-backup-info.txt') -Encoding UTF8
if ($newFiles.Count -gt 0) {
    $newFiles | Set-Content -LiteralPath (Join-Path $backupDir 'new-files.txt') -Encoding UTF8
}

function Restore-Backup {
    foreach ($entry in $entries) {
        $rel = ([string]$entry.path).Replace('/', '\')
        $backupFile = Join-Path $backupDir $rel
        $targetFile = Join-Path $InstallDir $rel
        if (Test-Path -LiteralPath $backupFile) {
            Copy-Item -LiteralPath $backupFile -Destination $targetFile -Force
        } elseif ($newFiles.Contains($rel)) {
            Remove-Item -LiteralPath $targetFile -Force -ErrorAction SilentlyContinue
        }
    }
}

# --- Apply (version.json last) ---------------------------------------------
$ordered = @($entries | Where-Object { ([string]$_.path) -ine 'version.json' }) +
           @($entries | Where-Object { ([string]$_.path) -ieq 'version.json' })

# Copy first, close the app afterwards. The app-triggered updater is a child of
# the app, so killing the app before the copy is what left a half-finished run
# with nothing on disk (17 Nov 2026). None of these files are locked while the
# app runs, and the app is restarted below either way.
try {
    Write-Host 'Copying files...'

    foreach ($entry in $ordered) {
        $rel = ([string]$entry.path).Replace('/', '\')
        Write-PatchLog ("copy: " + $rel)
        $src = Join-Path $PayloadDir $rel
        $dst = Join-Path $InstallDir $rel
        $dstParent = Split-Path -Parent $dst
        if (-not (Test-Path -LiteralPath $dstParent)) {
            New-Item -ItemType Directory -Path $dstParent -Force | Out-Null
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }

    Write-Host 'Verifying...'
    $bad = @()
    foreach ($entry in $entries) {
        $rel = ([string]$entry.path).Replace('/', '\')
        $dst = Join-Path $InstallDir $rel
        if (-not (Test-Path -LiteralPath $dst)) { $bad += "$rel (missing)"; continue }
        $actual = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = ([string]$entry.sha256).ToLowerInvariant()
        if ($actual -ne $expected) { $bad += $rel }
    }
    if ($bad.Count -gt 0) {
        throw ('Checksum mismatch after copy: ' + ($bad -join ', '))
    }
    Write-PatchLog 'verify: ok'
} catch {
    Write-PatchLog ("FAILED: " + $_.Exception.Message)
    Write-Host ''
    Write-Host "Patch failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Restoring the backup...' -ForegroundColor Yellow
    Restore-Backup
    Write-PatchLog ("rollback: " + $backupDir)
    Write-Host "Rolled back. Backup kept at $backupDir" -ForegroundColor Yellow
    throw 'Patch was not applied.'
}

# --- Done -------------------------------------------------------------------
$now = Read-Version (Join-Path $InstallDir 'version.json')
Write-Host ''
Write-Host ("Applied " + (Format-Version $patchVersion) + '.') -ForegroundColor Green
if ($null -ne $now) { Write-Host ("Installed version is now " + (Format-Version $now) + '.') }
Write-Host "Backup: $backupDir"
Write-PatchLog ("applied: " + (Format-Version $patchVersion))

if ($NoStart) {
    Write-Host 'Not starting the app (-NoStart).'
    Write-PatchLog 'not restarting (-NoStart)'
} elseif ($appWasRunning) {
    # Nothing in a patch needs the Python process to restart, and starting a new
    # instance would open a second browser tab. The running app serves the new
    # files on the next reload.
    Write-Host 'WYSIWYG is running - reload its tab to use the new version.'
    Write-PatchLog 'app was running - no second instance, reload picks up the change'
} else {
    Write-Host 'Starting WYSIWYG...'
    Write-PatchLog 'starting WYSIWYG (it was not running)'
    Start-Process -FilePath (Join-Path $InstallDir 'WYSIWYG.exe') -WorkingDirectory $InstallDir
}
