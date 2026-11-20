@echo off

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

REM --- 1. Browser windows that show the local app ---------------------------
echo Closing browser windows that show the local app...
if exist "%~dp0close_local_chrome.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0close_local_chrome.ps1" >nul 2>&1
    echo   done.
) else (
    echo   skipped        close_local_chrome.ps1 is not next to this script.
)

@echo off
REM Dev helper: close the source-run app, the scanner and their browser windows so
REM the next launch picks up the current files. See kill-wysiwyg.ps1 for switches
REM (-NoChrome, -WhatIf).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill-wysiwyg.ps1"
if errorlevel 1

pause