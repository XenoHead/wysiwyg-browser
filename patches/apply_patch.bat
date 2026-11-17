@echo off
rem Applies this patch to the installed WYSIWYG. See README.md one folder up.
rem   apply_patch.bat            ask, apply, restart
rem   apply_patch.bat -Yes       no confirmation
rem   apply_patch.bat -NoStart   do not restart the app
rem   apply_patch.bat -DryRun    check only, change nothing
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_patch.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo Patch failed with exit code %RC%.
    pause
)
endlocal
exit /b %RC%
