@echo off
REM ===========================================================================
REM  run_me_Installer.bat
REM  Installs WYSIWYG: closes everything that can hold the app (or its
REM  ChromeExt files) open, refreshes the WYSIWYG.old backup, then runs
REM  INSTALL_WYSIWYG.exe from this folder.
REM
REM  Like kill_wysiwyg.bat, it REPORTS every process it stopped or skipped, so a
REM  blocked install is obvious instead of silent. UberPaste is shut down too,
REM  because the installer replaces its files as well.
REM
REM  Safe to run whether or not anything is running. Works from the repo folder
REM  and from the copy that ships next to INSTALL_WYSIWYG.exe.
REM ===========================================================================
setlocal

echo ============================================================
echo  WYSIWYG installer
echo ============================================================
echo.

if not exist "%~dp0INSTALL_WYSIWYG.exe" (
    echo ERROR: INSTALL_WYSIWYG.exe is not in this folder:
    echo        %~dp0
    echo.
    pause
    endlocal
    exit /b 1
)

REM --- 1. Browser windows that show the local app ---------------------------
echo Closing browser windows that show the local app...
if exist "%~dp0close_local_chrome.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0close_local_chrome.ps1" >nul 2>&1
    echo   done.
) else (
    echo   skipped        close_local_chrome.ps1 is not next to this script.
)
echo.

REM --- 2. The app, the scanner and the chat --------------------------------
echo Closing local processes...
if exist "%~dp0kill-wysiwyg.ps1" (
    REM Same reporting as kill_wysiwyg.bat: stopped / skipped / left alone.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill-wysiwyg.ps1"
) else (
    echo   kill-wysiwyg.ps1 not found next to this script - using the built-in fallback.
    call :stopexe "WYSIWYG.exe"  "WYSIWYG app"
    call :stopexe "WysiScan.exe" "WysiScan scanner"
    call :stopexe "Wysichat.exe" "WysiChat"
    call :stopsource "scanner_server\.py|\\main\.py" "app/scanner from source"
)

REM --- 3. UberPaste ---------------------------------------------------------
REM kill-wysiwyg.ps1 deliberately leaves UberPaste alone (it is a separate
REM tool), but the installer overwrites its files, so stop it here: both a
REM built UberPaste.exe and a copy started with "python ...\UberPaste.py".
echo.
echo Closing UberPaste...
call :stopexe "UberPaste.exe" "UberPaste exe"
call :stopsource "UberPaste\.py" "UberPaste from source"

REM `timeout` errors out when there is no interactive console; ping waits silently.
echo.
echo Waiting for the files to be released...
ping -n 4 127.0.0.1 >nul
taskkill /F /T /IM WYSIWYG.exe >nul 2>&1
ping -n 3 127.0.0.1 >nul

REM --- 4. Refresh the backup ------------------------------------------------
echo.
echo Refreshing the backup of the installed app...
if exist "C:\FYRTOOLS\wysiwyg.old" (
    echo   Deleting the previous backup: C:\FYRTOOLS\wysiwyg.old
    rmdir /S /Q "C:\FYRTOOLS\wysiwyg.old"
)
if exist "C:\FYRTOOLS\wysiwyg" (
    echo   Copying C:\FYRTOOLS\wysiwyg to C:\FYRTOOLS\wysiwyg.old
    xcopy "C:\FYRTOOLS\wysiwyg" "C:\FYRTOOLS\wysiwyg.old" /E /I /Y /Q >nul 2>&1
    if errorlevel 1 (
        echo   WARNING        the backup did not finish - something may still be using the folder.
    ) else (
        echo   Backup complete.
    )
) else (
    echo   skipped        nothing to back up: C:\FYRTOOLS\wysiwyg does not exist yet.
)

REM --- 5. Installer ---------------------------------------------------------
echo.
echo Launching INSTALL_WYSIWYG.exe...
echo.
"%~dp0INSTALL_WYSIWYG.exe"
set "INSTALL_RC=%ERRORLEVEL%"
echo.
if "%INSTALL_RC%"=="0" (
    echo Installer finished.
) else (
    echo Installer exited with code %INSTALL_RC%.
)
echo.
pause
endlocal
exit /b 0


REM ===========================================================================
REM  Helpers
REM ===========================================================================

:stopexe
REM %1 = image name, %2 = label. Reports whether it was running, then stops it,
REM then checks it really is gone (a locked process is the usual install blocker).
setlocal
tasklist /FI "IMAGENAME eq %~1" /NH 2>nul | find /I "%~1" >nul
if errorlevel 1 (
    echo   skipped        %~2 - not running
    endlocal
    exit /b 0
)
taskkill /F /T /IM "%~1" >nul 2>&1
tasklist /FI "IMAGENAME eq %~1" /NH 2>nul | find /I "%~1" >nul
if errorlevel 1 (
    echo   stopped        %~2
) else (
    echo   FAILED         %~2 - still running, try running this as administrator
)
endlocal
exit /b 0

:stopsource
REM %1 = regex matched against the command line, %2 = label. A scanner or app
REM started from source is "python.exe ...\scanner_server.py" / "...\main.py",
REM which /IM cannot target without also killing unrelated Python processes.
REM The stop is verified per pid, so a launcher that takes its child with it is
REM reported once, not twice.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -match '%~1' }); if ($p.Count -eq 0) { Write-Host '  skipped        %~2 - not running' } else { foreach ($x in $p) { try { Stop-Process -Id $x.ProcessId -Force -ErrorAction Stop } catch { }; if (Get-Process -Id $x.ProcessId -ErrorAction SilentlyContinue) { Write-Host ('  FAILED         %~2 (pid ' + $x.ProcessId + ') - still running') } else { Write-Host ('  stopped        %~2 (pid ' + $x.ProcessId + ')') } } }"
endlocal
exit /b 0
