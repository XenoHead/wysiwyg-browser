<#
.SYNOPSIS
    Builds a WYSIWYG loose-file patch from this repository.

.DESCRIPTION
    Copies the selected runtime files plus version.json/changelog.txt into
    patches\out\<version>\files\, writes patch.json (version, note, per-file
    SHA-256) and drops apply_patch.bat/.ps1 next to them.

    Only files that main.py's resource_path() reads from the install folder are
    allowed. Python and other bundled code cannot be patched at runtime, so a
    changed non-whitelisted file aborts the build.

.PARAMETER Note
    One line describing the patch. Shown by apply_patch before it runs.

.PARAMETER Changed
    Pick up every modified/untracked file from "git status" that is patchable.

.PARAMETER Files
    Explicit list, e.g. -Files app.js,index.html. Relative to the repo root.

.PARAMETER Publish
    Robocopy the finished folder to <ShareRoot>\patches\<version>\.

.PARAMETER ShareRoot
    Published WYSIWYG folder. Defaults to the FYR share.

.EXAMPLE
    .\make_patch.bat -Note "multi-medium descriptions" -Changed

.EXAMPLE
    .\make_patch.bat -Note "typo in key features" -Files app.js -Publish
#>
[CmdletBinding()]
param(
    [string]$Note = '',

    [switch]$Changed,

    [string[]]$Files = @(),

    [switch]$List,

    [switch]$Publish,

    [switch]$AllowStaleRepo,

    [string]$ShareRoot = '\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG',

    [switch]$Delta
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$OutRoot = Join-Path $PSScriptRoot 'out'

# Files resource_path() will read from the install folder. Conditions.json is
# absent on purpose: it holds each machine's own favourites and edits.
$AllowedFiles = @(
    'app.js', 'index.html', 'editor.html', 'admin.html', 'search.html',
    'style_guide.html', 'styles.css',
    'data.json', 'media_formats.json', 'colourmap.json', 'colourrules.json',
    'version.json', 'changelog.txt',
    'fyrlogo.png', 'fyrlogo.ico', 'fyr-sign-front.png'
)
$AllowedPrefixes = @('ChromeExt\')

# Not shipped and not worth complaining about: docs, tooling, runtime litter.
$IgnoredPrefixes = @(
    '.continuity\', '.vscode\', 'docs\', 'tmp\', 'scratch\', 'patches\',
    'build\', 'dist\', 'dist_install\', 'Listings\'
)
$IgnoredFiles = @(
    'f0t_last.txt', 'wysiwyg_history.json', 'test_results.json',
    'discogs_last_extract.json', 'walmart_context_cache.json',
    'clipboard_history.json', 'SESSION_HANDOFF.md'
)

function Normalize-Rel([string]$rel) {
    return $rel.Replace('/', '\').Trim()
}

function Test-Allowed([string]$rel) {
    foreach ($prefix in $AllowedPrefixes) {
        if ($rel.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($name in $AllowedFiles) {
        if ($rel -ieq $name) { return $true }
    }
    return $false
}

function Test-Ignored([string]$rel) {
    foreach ($prefix in $IgnoredPrefixes) {
        if ($rel.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($name in $IgnoredFiles) {
        if ($rel -ieq $name) { return $true }
    }
    if ($rel -ieq '.gitignore') { return $true }
    if ($rel -like '*.md') { return $true }
    if ($rel -like '*.log') { return $true }
    # Repo-side build/release tooling: not part of the running app.
    if ($rel -like '*.bat') { return $true }
    if ($rel -like '*.iss') { return $true }
    return $false
}

function Get-ChangedPaths {
    param([switch]$Quiet)

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'git was not found on PATH. Name the files with -Files instead.'
    }
    $lines = & git -C $RepoRoot status --porcelain=v1 --untracked-files=all
    if ($LASTEXITCODE -ne 0) { throw "git status failed in $RepoRoot." }

    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.Length -lt 4) { continue }
        $xy = $line.Substring(0, 2)
        $path = $line.Substring(3).Trim()
        if ($path -like '* -> *') { $path = ($path -split ' -> ')[-1] }
        $path = $path.Trim('"')
        if ($xy.Contains('D')) {
            if (-not $Quiet) {
                Write-Host "  deleting $path - a patch cannot delete files, skipping" -ForegroundColor DarkYellow
            }
            continue
        }
        $paths.Add($path)
    }
    return $paths
}

# --- Machine-readable change list (used by patch_gui.py) --------------------
if ($List) {
    $allowed = New-Object System.Collections.Generic.List[object]
    $blocked = New-Object System.Collections.Generic.List[string]

    foreach ($rel in Get-ChangedPaths -Quiet) {
        $n = Normalize-Rel $rel
        if (Test-Ignored $n) { continue }
        if (Test-Allowed $n) {
            $full = Join-Path $RepoRoot $n
            if (Test-Path -LiteralPath $full -PathType Leaf) {
                $allowed.Add([pscustomobject]@{
                    path = $n
                    size = (Get-Item -LiteralPath $full).Length
                })
            }
            continue
        }
        $blocked.Add($n)
    }

    $versionFile = Join-Path $RepoRoot 'version.json'
    $verObj = Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json
    $version = '{0}.{1}.{2}.{3}' -f ([int]$verObj.major), ([int]$verObj.minor), ([int]$verObj.patch), ([int]$verObj.build)

    $result = [pscustomobject]@{
        version = $version
        repo    = $RepoRoot
        files   = [object[]]$allowed
        blocked = [object[]]$blocked
    }
    $result | ConvertTo-Json -Depth 4
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Note)) {
    throw 'A note is required: -Note "what this patch fixes".'
}

# --- GOD repo rule ----------------------------------------------------------
# This checkout is the master copy. Never build a patch from it while the
# server has a newer patch, or the new patch would fork from stale files.
# (build_full.ps1 -SyncOnly pulls the newer patches in.)
if (-not $AllowStaleRepo) {
    $staleMessage = $null
    try {
        $verRaw = Get-Content -LiteralPath (Join-Path $RepoRoot 'version.json') -Raw | ConvertFrom-Json
        $repoVer = [version]('{0}.{1}.{2}.{3}' -f [int]$verRaw.major, [int]$verRaw.minor, [int]$verRaw.patch, [int]$verRaw.build)
        $patchesDir = Join-Path $ShareRoot 'patches'
        if (Test-Path -LiteralPath $patchesDir) {
            $newest = $null
            foreach ($folder in @(Get-ChildItem -LiteralPath $patchesDir -Directory -ErrorAction SilentlyContinue)) {
                $manifest = Join-Path $folder.FullName 'patch.json'
                if (-not (Test-Path -LiteralPath $manifest)) { continue }
                try {
                    $v = (Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).version
                    $pv = [version]('{0}.{1}.{2}.{3}' -f [int]$v.major, [int]$v.minor, [int]$v.patch, [int]$v.build)
                    if (-not $newest -or $pv -gt $newest) { $newest = $pv }
                } catch { }
            }
            if ($newest -and $newest -gt $repoVer) {
                $staleMessage = ("This repo is at {0} but the server already has patch {1}. " +
                    "Pull it in first so the master copy stays the newest:" +
                    "`n    powershell -File patches\build_full.ps1 -SyncOnly" +
                    "`n(or the Full installer tab > 'Pull missing patches into this repo')") -f $repoVer.ToString(), $newest.ToString()
            }
        }
    } catch {
        Write-Host ("Could not check the server for newer patches: " + $_.Exception.Message) -ForegroundColor DarkYellow
    }
    if ($staleMessage) { throw $staleMessage }
}

# --- Select the payload -----------------------------------------------------
$selected = New-Object System.Collections.Generic.List[string]

if ($Changed) {
    $offenders = New-Object System.Collections.Generic.List[string]
    foreach ($rel in Get-ChangedPaths) {
        $n = Normalize-Rel $rel
        if (Test-Ignored $n) { continue }
        if (Test-Allowed $n) {
            if (-not $selected.Contains($n)) { $selected.Add($n) }
            continue
        }
        $offenders.Add($n)
    }
    if ($offenders.Count -gt 0) {
        Write-Host ''
        Write-Host 'These changed files cannot ship in a loose-file patch:' -ForegroundColor Yellow
        $offenders | ForEach-Object { Write-Host "  $_" }
        Write-Host ''
        throw 'Python or bundled code changed. Run !build.bat for those, or build a patch that excludes them with -Files.'
    }
}

# "-File script.ps1 -Files a.js,b.html" hands the whole comma list over as ONE
# string (unlike running the script inside a PowerShell session), so split it
# here before validating. Same for the .bat wrapper and the GUI.
$fileArgs = New-Object System.Collections.Generic.List[string]
foreach ($entry in $Files) {
    foreach ($part in ([string]$entry -split ',')) {
        if (-not [string]::IsNullOrWhiteSpace($part)) { $fileArgs.Add($part.Trim()) }
    }
}

foreach ($rel in $fileArgs) {
    $n = Normalize-Rel $rel
    if (-not (Test-Allowed $n)) {
        throw "'$n' is not a patchable loose file - see patches\README.md."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot $n) -PathType Leaf)) {
        throw "'$n' does not exist in $RepoRoot."
    }
    if (-not $selected.Contains($n)) { $selected.Add($n) }
}

# --- Roll up earlier published patches (cumulative by default) ---------------
# A patch that only carries its own delta would leave a user who skipped
# intermediate versions missing those changes. Roll every published patch that
# is still newer than the last full installer into this one, so applying the
# newest patch always gives the user everything. Use -Delta to ship a pure
# delta instead (rare).
if (-not $Delta) {
    $baselineVer = [version]'0.0.0.0'
    $serverVersionPath = Join-Path (Join-Path $ShareRoot 'WYSIWYG') 'version.json'
    try {
        if (Test-Path -LiteralPath $serverVersionPath) {
            $iv = Get-Content -LiteralPath $serverVersionPath -Raw | ConvertFrom-Json
            $baselineVer = [version]('{0}.{1}.{2}.{3}' -f [int]$iv.major, [int]$iv.minor, [int]$iv.patch, [int]$iv.build)
        }
    } catch { }

    $patchesDir = Join-Path $ShareRoot 'patches'
    if (Test-Path -LiteralPath $patchesDir) {
        $published = @(
            Get-ChildItem -LiteralPath $patchesDir -Directory -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $m = Join-Path $_.FullName 'patch.json'
                    if (-not (Test-Path -LiteralPath $m)) { return }
                    try {
                        $d = Get-Content -LiteralPath $m -Raw | ConvertFrom-Json
                        $v = [version]('{0}.{1}.{2}.{3}' -f [int]$d.version.major, [int]$d.version.minor, [int]$d.version.patch, [int]$d.version.build)
                        if ($v -gt $baselineVer) {
                            [pscustomobject]@{ Version = $v; Manifest = $d }
                        }
                    } catch { }
                }
        )
        $rolledUp = 0
        foreach ($p in ($published | Sort-Object Version)) {
            foreach ($f in ($p.Manifest.files)) {
                $rel = Normalize-Rel $f.path
                if (Test-Ignored $rel) { continue }
                if (-not (Test-Allowed $rel)) { continue }
                $full = Join-Path $RepoRoot $rel
                if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
                if (-not $selected.Contains($rel)) {
                    $selected.Add($rel)
                    $rolledUp++
                }
            }
        }
        if ($rolledUp -gt 0) {
            Write-Host ("Rolled up {0} file(s) from published patches newer than the installer baseline ({1})." -f $rolledUp, $baselineVer.ToString()) -ForegroundColor Cyan
        }
    }
}

# A patch always carries these, so the client's version and notes advance.
foreach ($always in @('version.json', 'changelog.txt')) {
    if (Test-Path -LiteralPath (Join-Path $RepoRoot $always) -PathType Leaf) {
        if (-not $selected.Contains($always)) { $selected.Add($always) }
    }
}

if ($selected.Count -eq 0) {
    throw 'Nothing selected. Use -Changed, or name files with -Files.'
}

# --- Version ----------------------------------------------------------------
$versionFile = Join-Path $RepoRoot 'version.json'
if (-not (Test-Path -LiteralPath $versionFile)) { throw "Missing $versionFile." }
$verObj = Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json
$version = '{0}.{1}.{2}.{3}' -f ([int]$verObj.major), ([int]$verObj.minor), ([int]$verObj.patch), ([int]$verObj.build)

# --- Build the folder -------------------------------------------------------
$outDir = Join-Path $OutRoot $version
if (Test-Path -LiteralPath $outDir) {
    Write-Host "Replacing the previous build of $version." -ForegroundColor DarkYellow
    Remove-Item -LiteralPath $outDir -Recurse -Force
}
$filesDir = Join-Path $outDir 'files'
New-Item -ItemType Directory -Path $filesDir -Force | Out-Null

$entries = New-Object System.Collections.Generic.List[object]
foreach ($rel in $selected) {
    $src = Join-Path $RepoRoot $rel
    $dst = Join-Path $filesDir $rel
    $dstParent = Split-Path -Parent $dst
    if (-not (Test-Path -LiteralPath $dstParent)) {
        New-Item -ItemType Directory -Path $dstParent -Force | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $entries.Add([pscustomobject]@{
        path   = $rel.Replace('\', '/')
        sha256 = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant()
        size   = (Get-Item -LiteralPath $dst).Length
    })
}

# The applier is shipped inside the patch so it works straight off the share.
foreach ($tool in @('apply_patch.bat', 'apply_patch.ps1')) {
    $toolPath = Join-Path $PSScriptRoot $tool
    if (-not (Test-Path -LiteralPath $toolPath)) { throw "Missing $toolPath." }
    Copy-Item -LiteralPath $toolPath -Destination (Join-Path $outDir $tool) -Force
}
foreach ($tool in @('kill-wysiwyg.ps1', 'close_local_chrome.ps1')) {
    $toolPath = Join-Path $RepoRoot $tool
    if (Test-Path -LiteralPath $toolPath) {
        Copy-Item -LiteralPath $toolPath -Destination (Join-Path $outDir $tool) -Force
    }
}

$manifest = [pscustomobject]@{
    version = [pscustomobject]@{
        major = [int]$verObj.major
        minor = [int]$verObj.minor
        patch = [int]$verObj.patch
        build = [int]$verObj.build
    }
    note    = $Note
    created = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    # [object[]] rather than @(): Windows PowerShell 5.1 throws
    # "Argument types do not match" for @() around a generic List in a hashtable.
    files   = [object[]]$entries
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outDir 'patch.json') -Encoding UTF8

# --- Report -----------------------------------------------------------------
Write-Host ''
Write-Host "Patch built: patches\out\$version" -ForegroundColor Green
Write-Host "  note : $Note"
Write-Host ('  files: ' + (($entries | ForEach-Object { $_.path }) -join ', '))
Write-Host ('  size : {0:N0} KB' -f ((($entries | Measure-Object -Property size -Sum).Sum) / 1KB))
Write-Host ''

if ($Publish) {
    if (-not (Test-Path -LiteralPath $ShareRoot)) {
        throw "Share not reachable: $ShareRoot"
    }
    $target = Join-Path $ShareRoot (Join-Path 'patches' $version)
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    & robocopy $outDir $target /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE." }
    Write-Host "Published: $target" -ForegroundColor Green
    Write-Host "Clients run: $target\apply_patch.bat"
} else {
    Write-Host "Publish with: patches\make_patch.bat -Note `"$Note`" -Changed -Publish"
    Write-Host "Or copy patches\out\$version to $ShareRoot\patches\$version"
}
