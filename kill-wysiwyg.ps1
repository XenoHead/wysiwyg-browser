<#
    kill-wysiwyg.ps1
    Closes the local WYSIWYG app/scanner and REPORTS what it did - what it
    stopped, what was not running, and what it deliberately left alone.

    Kills:   WYSIWYG.exe, WysiScan.exe, Wysichat.exe
             a WysiScan started from SOURCE (python.exe ...\scanner_server.py)
             the app started from SOURCE (python.exe ...\main.py)
             whatever owns ports 8008 / 8010 (catches elevated processes whose
             command line a non-elevated caller cannot read)
    Waits:   until ports 8008 and 8010 are actually free (max ~20s)

    Browser windows are deliberately left alone - only run_me_Installer.bat
    closes those (via close_local_chrome.ps1).

    Switches:
      -WhatIf   report what would be stopped, change nothing
      -Quiet    summary line only
#>
[CmdletBinding()]
param(
    [switch]$WhatIf,
    [switch]$Quiet
)

$ports = 8008, 8010
$rows = New-Object System.Collections.ArrayList
function Add-Row($label, $status, $detail) {
    [void]$rows.Add([pscustomobject]@{ Label = $label; Status = $status; Detail = $detail })
}
function Say($msg) { if (-not $Quiet) { Write-Host $msg } }

# --- 1. The app's own exes ----------------------------------------------------
foreach ($exe in 'WYSIWYG.exe', 'WysiScan.exe', 'Wysichat.exe') {
    $procs = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($exe)) -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { Add-Row $exe 'not running' ''; continue }
    foreach ($p in $procs) { Add-Row $exe 'stop' "pid $($p.Id)" ; $rows[-1] | Add-Member -NotePropertyName Id -NotePropertyValue $p.Id }
}

# --- 2. Python processes started from source ---------------------------------
$leftAlone = 0
foreach ($p in (Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'python.exe', 'pythonw.exe' })) {
    $cmd = [string]$p.CommandLine
    $label = $null
    if ($cmd -like '*scanner_server.py*') { $label = 'scanner (source)' }
    elseif ($cmd -like '*main.py*') { $label = 'app (source)' }
    if (-not $label) { $leftAlone++; continue }
    Add-Row $label 'stop' "pid $($p.ProcessId)"
    $rows[-1] | Add-Member -NotePropertyName Id -NotePropertyValue $p.ProcessId
}
if ($leftAlone -gt 0) { Add-Row 'other python' 'left alone' "$leftAlone process(es), e.g. UberPaste" }

# --- 3. Whatever is listening on the app ports --------------------------------
# Reported even when the owner is already queued above, so the output shows which
# process was holding the port instead of silently dropping the line.
$portOwners = @{}
foreach ($listenPort in $ports) {
    $conns = @(Get-NetTCPConnection -LocalPort $listenPort -State Listen -ErrorAction SilentlyContinue)
    if ($conns.Count -eq 0) { Add-Row "port $listenPort" 'not listening' ''; continue }
    foreach ($c in $conns) {
        $ownerId = $c.OwningProcess
        if (-not $ownerId) { continue }
        $ownerName = (Get-Process -Id $ownerId -ErrorAction SilentlyContinue).ProcessName
        if (-not $ownerName) { $ownerName = 'unknown' }
        $portOwners[$ownerId] = $listenPort
        $already = $rows | Where-Object { $_.Id -eq $ownerId } | Select-Object -First 1
        if ($already) {
            Add-Row "port $listenPort" 'already listed' "owner: $ownerName (pid $ownerId)"
        } else {
            Add-Row "port $listenPort" 'stop' "owner: $ownerName (pid $ownerId)"
            $rows[-1] | Add-Member -NotePropertyName Id -NotePropertyValue $ownerId
        }
    }
}

# --- 4. Do it (or say what would happen) -------------------------------------
$stopped = 0
$failed = 0
foreach ($r in $rows) {
    switch ($r.Status) {
        'stop' {
            if ($WhatIf) { Say ("  would stop   {0,-16} {1}" -f $r.Label, $r.Detail); $stopped++; continue }
            try {
                Stop-Process -Id $r.Id -Force -ErrorAction Stop
                Say ("  stopped      {0,-16} {1}" -f $r.Label, $r.Detail); $stopped++
            } catch {
                Say ("  FAILED       {0,-16} {1}: {2}" -f $r.Label, $r.Detail, $_.Exception.Message)
                $failed++
            }
        }
        'not running'    { Say ("  skipped      {0,-16} not running" -f $r.Label) }
        'not listening'  { Say ("  skipped      {0,-16} not listening"  -f $r.Label) }
        'already listed' { Say ("  listed above {0,-16} {1}" -f $r.Label, $r.Detail) }
        'left alone'     { Say ("  left alone   {0,-16} {1}" -f $r.Label, $r.Detail) }
    }
}

if ($WhatIf) { Say 'WhatIf: nothing was stopped.'; return }

# --- 5. Wait for the ports, then report ---------------------------------------
$stillHeld = @()
foreach ($listenPort in $ports) {
    for ($i = 0; $i -lt 40; $i++) {
        if (-not (Get-NetTCPConnection -LocalPort $listenPort -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    $held = Get-NetTCPConnection -LocalPort $listenPort -State Listen -ErrorAction SilentlyContinue
    if ($held) {
        $ownerId = ($held | Select-Object -First 1).OwningProcess
        $ownerName = (Get-Process -Id $ownerId -ErrorAction SilentlyContinue).ProcessName
        $stillHeld += "port $listenPort (pid $ownerId $ownerName)"
    }
}

if ($stillHeld.Count -gt 0) {
    Say ("WARNING: still in use -> {0}. Try running this as administrator." -f ($stillHeld -join ', '))
} else {
    Say ("Done. {0} stopped, {1} failed. Ports {2} are free." -f $stopped, $failed, ($ports -join '/'))
}
