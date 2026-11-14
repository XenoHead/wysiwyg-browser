@echo off
REM Closes everything that can hold the app (or its ChromeExt files) open, then
REM runs the installer. Safe to run with the app running or not.
REM /F = force, /T = kill the whole process tree (including child processes like
REM the scanner subprocess that can keep the EXE file handle locked).
setlocal

echo Closing browser windows that show the local app...
if exist "%~dp0close_local_chrome.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0close_local_chrome.ps1" >nul 2>&1
) else (
    echo   close_local_chrome.ps1 not found next to this script - skipping.
)

taskkill /F /T /IM WYSIWYG.exe >nul 2>&1
taskkill /F /T /IM WysiScan.exe >nul 2>&1
taskkill /F /T /IM Wysichat.exe >nul 2>&1

REM WysiScan started from SOURCE runs as "python.exe ...\scanner_server.py", which
REM /IM cannot target without also killing the main app's Python process. Match on
REM the command line instead.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -like '*scanner_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

REM `timeout` errors out when there is no interactive console; ping waits silently.
ping -n 4 127.0.0.1 >nul
taskkill /F /T /IM WYSIWYG.exe >nul 2>&1
ping -n 3 127.0.0.1 >nul

echo Done killing processes.
echo.
echo.
echo Backing up current WYSIWYG to WYSIWYG.old. 
if exist "C:\FYRTOOLS\wysiwyg.old" rmdir /S /Q "C:\FYRTOOLS\wysiwyg.old"
xcopy "C:\FYRTOOLS\wysiwyg" "C:\FYRTOOLS\wysiwyg.old" /E /I /Y /Q >nul 2>&1
echo.
echo.
echo Backup complete.
echo.
echo.
echo.
echo Launching installer...

REM Run INSTALL_WYSIWYG.exe located in the same directory as this batch script
"%~dp0INSTALL_WYSIWYG.exe"

endlocal
