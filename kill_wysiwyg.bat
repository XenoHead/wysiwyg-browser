@echo off
REM Kills any running WYSIWYG / WysiScan / WysiChat processes so the installer
REM can overwrite them, and REPORTS what it stopped and what it skipped.
REM Run this manually if an install is blocked by a "file in use" / locked
REM WYSIWYG.exe error, then launch INSTALL_WYSIWYG.exe.
setlocal

echo Cleaning up local WYSIWYG processes...
echo.

if exist "%~dp0kill-wysiwyg.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill-wysiwyg.ps1"
) else (
    REM Fallback when the .ps1 is not next to this script - no reporting, but it
    REM still clears the common cases.
    taskkill /F /T /IM WYSIWYG.exe
    taskkill /F /T /IM WysiScan.exe
    taskkill /F /T /IM Wysichat.exe
    ping -n 4 127.0.0.1 >nul
)

echo.
echo You can now run the installer.
endlocal
