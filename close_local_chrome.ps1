<#
    close_local_chrome.ps1
    Closes browser windows/tabs showing the local WYSIWYG pages (127.0.0.1:8008 and
    :8010) so nothing holds the app or ChromeExt files open during an install.

    Only windows whose caption STARTS WITH one of the known page titles are
    touched, and only when the owning process is a browser. Chrome offers no way
    to close a single tab from outside, so this closes the whole window that is
    showing that page (its other tabs with it).

    -ListOnly  just prints what would be closed.
#>
param([switch]$ListOnly)

Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class LocalWindowCloser {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
}
"@

# Page titles of the local app (see <title> in index.html / Adds pages / scanner).
$prefixes = @(
    'WYSIWYG',                       # main app tab (8008)
    'WysiScan',                      # scanner page (8010)
    'Extract Text From Image(s)'     # scanner's own window
)

# Only close windows owned by a browser, never another app that happens to share a title.
$browsers = @('chrome', 'msedge', 'brave', 'chromium', 'vivaldi')

$found = New-Object System.Collections.ArrayList
$closed = 0

$callback = {
    param([IntPtr]$hWnd, [IntPtr]$lParam)

    $sb = New-Object System.Text.StringBuilder 512
    [void][LocalWindowCloser]::GetWindowText($hWnd, $sb, 512)
    $title = $sb.ToString()
    if ([string]::IsNullOrWhiteSpace($title)) { return $true }

    $isMatch = $false
    foreach ($p in $prefixes) {
        if ($title.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase)) { $isMatch = $true; break }
    }
    if (-not $isMatch) { return $true }

    $procId = 0
    [void][LocalWindowCloser]::GetWindowThreadProcessId($hWnd, [ref]$procId)
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $proc) { return $true }
    if ($browsers -notcontains $proc.ProcessName.ToLower()) { return $true }

    [void]$found.Add([pscustomobject]@{ Title = $title; Browser = $proc.ProcessName; Pid = $procId })

    if (-not $ListOnly) {
        # WM_CLOSE = polite close, same as clicking the X
        [void][LocalWindowCloser]::PostMessage($hWnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
        $script:closed++
    }
    return $true
}

[void][LocalWindowCloser]::EnumWindows($callback, [IntPtr]::Zero)

if ($ListOnly) {
    if ($found.Count -gt 0) {
        Write-Host "Browser windows showing the local app:"
        $found | ForEach-Object { Write-Host ("  [{0}] {1}  (pid {2})" -f $_.Browser, $_.Title, $_.Pid) }
    } else {
        Write-Host "No browser windows showing the local app."
    }
} else {
    if ($closed -gt 0) { Write-Host "Closed $closed app browser window(s)." }
    else { Write-Host "No app browser windows to close." }
}
