@echo off
REM Dev helper: close the source-run app, the scanner and their browser windows so
REM the next launch picks up the current files. See kill-wysiwyg.ps1 for switches
REM (-NoChrome, -WhatIf).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill-wysiwyg.ps1"
if errorlevel 1 pause
