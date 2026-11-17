<#
.SYNOPSIS
    Builds a full Inno Setup installer that already contains every published patch.

.DESCRIPTION
    Works out the version the installer should carry:

      target = highest of (repo version.json, published patch versions,
                           installer version already on the share)

    Then reports which published patches are "missing" (newer than the installer
    on the share). Patches never carry Python, so a patch newer than the repo is
    the only case where payload files are copied into the repo; a patch older
    than or equal to the repo is already included and its payload is ignored
    (the repo is newer).

    With -Check nothing is changed: it prints one JSON object for the GUI.
    Otherwise it bumps version.json + wysiWyg-installer.iss to the target,
    applies any newer patch payload over the repo (with a backup), runs
    !build.bat, compiles the .iss with ISCC and optionally publishes the
    installer to the share.

.PARAMETER ShareRoot
    Published WYSIWYG folder (installer + version.json + patches\).

.PARAMETER Publish
    Robocopy dist_install\* to the share after a successful build.

.PARAMETER Check
    Print JSON and exit. Changes nothing.

.PARAMETER Iscc
    Path to ISCC.exe. Defaults to the usual Inno Setup 6 locations.

.PARAMETER SyncOnly
    Apply published patches newer than the repo (and bump version.json/.iss),
    then stop before building. Used by the GUI's "Sync repo" button.
#>
[CmdletBinding()]
param(
    [string]$ShareRoot = '\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG',
    [switch]$Publish,
    [switch]$Check,
    [string]$Iscc = '',
    [switch]$SyncOnly
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VersionFile = Join-Path $RepoRoot 'version.json'
$IssFile = Join-Path $RepoRoot 'wysiWyg-installer.iss'
$BuildBat = Join-Path $RepoRoot '!build.bat'
$DistDir = Join-Path $RepoRoot 'dist_install'
$ChangelogFile = Join-Path $RepoRoot 'changelog.txt'

function Write-Step([string]$message) {
    Write-Host ''
    Write-Host ("== " + $message) -ForegroundColor Cyan
}

function Read-VersionFile([string]$path) {
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

function To-Version($v) {
    return [version]('{0}.{1}.{2}.{3}' -f [int]$v.major, [int]$v.minor, [int]$v.patch, [int]$v.build)
}

function Get-PublishedPatches([string]$share) {
    $patchesDir = Join-Path $share 'patches'
    $list = New-Object System.Collections.Generic.List[object]
    if (-not (Test-Path -LiteralPath $patchesDir)) { return $list }

    foreach ($folder in @(Get-ChildItem -LiteralPath $patchesDir -Directory -ErrorAction SilentlyContinue)) {
        $manifest = Join-Path $folder.FullName 'patch.json'
        if (-not (Test-Path -LiteralPath $manifest)) { continue }
        try {
            $data = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
            $v = $data.version
            $version = [version]('{0}.{1}.{2}.{3}' -f [int]$v.major, [int]$v.minor, [int]$v.patch, [int]$v.build)
            $list.Add([pscustomobject]@{
                version = $version
                text    = $version.ToString()
                note    = [string]$data.note
                folder  = $folder.FullName
                files   = [object[]]@($data.files)
            })
        } catch {
            Write-Host ("Ignoring unreadable patch {0}: {1}" -f $folder.Name, $_.Exception.Message) -ForegroundColor DarkYellow
        }
    }
    return $list
}

function Get-RepoVersion {
    $v = Read-VersionFile $VersionFile
    if (-not $v) { throw "Missing or unreadable $VersionFile" }
    return To-Version $v
}

function Set-VersionFiles([version]$target) {
    $text = $target.ToString()
    $current = Get-Content -LiteralPath $VersionFile -Raw | ConvertFrom-Json
    if ($current.major -ne $target.Major -or $current.minor -ne $target.Minor -or
        $current.patch -ne $target.Build -or $current.build -ne $target.Revision) {
        $payload = [ordered]@{
            major = $target.Major
            minor = $target.Minor
            patch = $target.Build
            build = $target.Revision
        }
        $json = $payload | ConvertTo-Json
        [System.IO.File]::WriteAllText($VersionFile, $json + "`n")
        Write-Host ("version.json -> " + $text)
    }

    $iss = Get-Content -LiteralPath $IssFile -Raw
    $updated = [regex]::Replace($iss, '(#define\s+MyAppVersion\s+")[^"]*(")', ('${1}' + $text + '${2}'), 1)
    if ($updated -ne $iss) {
        # WriteAllText keeps the file's existing CRLF endings exactly.
        [System.IO.File]::WriteAllText($IssFile, $updated)
        Write-Host ("wysiWyg-installer.iss -> " + $text)
    }

    if (Test-Path -LiteralPath $ChangelogFile) {
        $head = (Get-Content -LiteralPath $ChangelogFile -TotalCount 1)
        if ($head -notmatch ('^### v' + [regex]::Escape($text) + '\b')) {
            Write-Host ("WARNING: changelog.txt has no '### v{0}' heading yet - add one if this is a release." -f $text) -ForegroundColor Yellow
        }
    }
}

# --- Work out the target ----------------------------------------------------
$repoVersion = Get-RepoVersion
$installerVersion = $null
$installerRaw = Read-VersionFile (Join-Path $ShareRoot 'version.json')
if ($installerRaw) { $installerVersion = To-Version $installerRaw }

$patches = @(Get-PublishedPatches $ShareRoot | Sort-Object version)
$newestPatch = $null
if ($patches.Count -gt 0) { $newestPatch = $patches[$patches.Count - 1].version }

$target = $repoVersion
foreach ($p in $patches) { if ($p.version -gt $target) { $target = $p.version } }
if ($installerVersion -and $installerVersion -gt $target) { $target = $installerVersion }

$missing = @($patches | Where-Object { -not $installerVersion -or $_.version -gt $installerVersion })
# A patch newer than the repo carries files the repo does not have yet. Older
# patches are already in the repo and must not be copied back over it.
$toApply = @($patches | Where-Object { $_.version -gt $repoVersion })
$buildNeeded = (-not $installerVersion) -or ($target -gt $installerVersion)
# Building a full installer at a version that is already a published patch means
# two different builds share a number, and machines already patched to it will
# never be offered the installer. Usually means "bump before building".
$sharedWithPatch = [bool]($newestPatch -and $target -eq $newestPatch -and $buildNeeded)

if ($Check) {
    $result = [pscustomobject]@{
        share             = $ShareRoot
        repo              = $repoVersion.ToString()
        installer         = $(if ($installerVersion) { $installerVersion.ToString() } else { $null })
        newest_patch      = $(if ($newestPatch) { $newestPatch.ToString() } else { $null })
        target            = $target.ToString()
        build_needed      = [bool]$buildNeeded
        shared_with_patch = [bool]$sharedWithPatch
        missing           = [object[]]@($missing | ForEach-Object { $_.text })
        to_apply          = [object[]]@($toApply | ForEach-Object { $_.text })
    }
    $result | ConvertTo-Json -Depth 4
    exit 0
}

Write-Host ''
Write-Host 'WYSIWYG full installer' -ForegroundColor White
Write-Host ("  repo         : " + $repoVersion.ToString())
Write-Host ("  on the share : " + $(if ($installerVersion) { $installerVersion.ToString() } else { '(no installer)' }))
Write-Host ("  newest patch : " + $(if ($newestPatch) { $newestPatch.ToString() } else { '(none)' }))
Write-Host ("  target       : " + $target.ToString()) -ForegroundColor Green
if ($missing.Count -gt 0) {
    Write-Host ("  missing      : " + (($missing | ForEach-Object { $_.text }) -join ', '))
} else {
    Write-Host '  missing      : none'
}

if (-not $buildNeeded) {
    Write-Host ''
    Write-Host ("The installer on the share is already at {0} - nothing to build." -f $installerVersion.ToString()) -ForegroundColor Green
    exit 0
}

if ($sharedWithPatch) {
    Write-Host ''
    Write-Host ("WARNING: {0} is already a published patch." -f $target.ToString()) -ForegroundColor Yellow
    Write-Host '  Machines already patched to that version will NOT be offered this installer,' -ForegroundColor Yellow
    Write-Host '  and two different builds would share one number. Bump the version first if this' -ForegroundColor Yellow
    Write-Host '  build contains Python changes (a patch cannot carry those).' -ForegroundColor Yellow
}

# --- Backup anything this touches -------------------------------------------
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path (Join-Path $PSScriptRoot 'out') ('_prebuild\' + $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item -LiteralPath $VersionFile -Destination $backupDir -Force
Copy-Item -LiteralPath $IssFile -Destination $backupDir -Force
Write-Host ("  backup       : " + $backupDir) -ForegroundColor DarkGray

# --- Apply patches that are newer than the repo -----------------------------
foreach ($patch in $toApply) {
    Write-Step ("Applying patch payload " + $patch.text)
    foreach ($entry in $patch.files) {
        $rel = ([string]$entry.path).Replace('/', '\')
        if ($rel -ieq 'version.json') { continue }   # set explicitly below
        $src = Join-Path (Join-Path $patch.folder 'files') $rel
        $dst = Join-Path $RepoRoot $rel
        if (-not (Test-Path -LiteralPath $src)) { throw "Patch $($patch.text) is missing files\$rel" }
        $actual = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$entry.sha256).ToLowerInvariant()) {
            throw "Patch $($patch.text): checksum mismatch for $rel"
        }
        if (Test-Path -LiteralPath $dst) {
            $backupFile = Join-Path $backupDir $rel
            $backupParent = Split-Path -Parent $backupFile
            if (-not (Test-Path -LiteralPath $backupParent)) {
                New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
            }
            Copy-Item -LiteralPath $dst -Destination $backupFile -Force
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-Host ("  copied " + $rel)
    }
}

# --- Version files ----------------------------------------------------------
Write-Step ("Setting version " + $target.ToString())
Set-VersionFiles $target

if ($SyncOnly) {
    Write-Host ''
    Write-Host ("Repo synced to " + $target.ToString() + " (no build requested).") -ForegroundColor Green
    exit 0
}

# --- Build ------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $BuildBat)) { throw "Missing $BuildBat" }
Write-Step 'Running !build.bat (PyInstaller) - this takes a few minutes'
& cmd.exe /c ('"' + $BuildBat + '"')
if ($LASTEXITCODE -ne 0) { throw "!build.bat failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'dist\WYSIWYG\WYSIWYG.exe'))) {
    throw '!build.bat did not produce dist\WYSIWYG\WYSIWYG.exe.'
}

# --- Compile the installer --------------------------------------------------
if ([string]::IsNullOrWhiteSpace($Iscc)) {
    foreach ($candidate in @(
            'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
            'C:\Program Files\Inno Setup 6\ISCC.exe')) {
        if (Test-Path -LiteralPath $candidate) { $Iscc = $candidate; break }
    }
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc)) {
    throw 'ISCC.exe not found. Pass -Iscc "C:\path\to\ISCC.exe".'
}
Write-Step 'Compiling the installer (ISCC)'
& $Iscc $IssFile
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE." }

$installerPath = Join-Path $DistDir 'INSTALL_WYSIWYG.exe'
if (-not (Test-Path -LiteralPath $installerPath)) {
    throw "ISCC did not produce $installerPath."
}
$built = Get-Item -LiteralPath $installerPath
$distVersion = Read-VersionFile (Join-Path $DistDir 'version.json')
if (-not $distVersion -or (To-Version $distVersion) -ne $target) {
    throw "dist_install\version.json does not read $($target.ToString()) - !build.bat may have used a stale file."
}

Write-Host ''
Write-Host ("Installer built: " + $installerPath) -ForegroundColor Green
Write-Host ("  version : " + $target.ToString())
Write-Host ("  size    : {0:N0} MB" -f ($built.Length / 1MB))

# --- Publish ----------------------------------------------------------------
if ($Publish) {
    if (-not (Test-Path -LiteralPath $ShareRoot)) { throw "Share not reachable: $ShareRoot" }
    Write-Step ("Publishing to " + $ShareRoot)
    & robocopy $DistDir $ShareRoot /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE." }
    $shareVersion = Read-VersionFile (Join-Path $ShareRoot 'version.json')
    if (-not $shareVersion -or (To-Version $shareVersion) -ne $target) {
        throw "The share's version.json does not read $($target.ToString()) after publishing."
    }
    Write-Host ("Published " + $target.ToString() + " to the share.") -ForegroundColor Green
}

Write-Host ''
Write-Host 'Done.' -ForegroundColor Green
