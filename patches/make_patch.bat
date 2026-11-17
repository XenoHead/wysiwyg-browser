@echo off
rem Builds a WYSIWYG loose-file patch. See README.md in this folder.
rem   make_patch.bat -Note "what it fixes" -Changed
rem   make_patch.bat -Note "what it fixes" -Files app.js,index.html -Publish
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_patch.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo Patch build failed with exit code %RC%.
    pause
)
endlocal
exit /b %RC%
