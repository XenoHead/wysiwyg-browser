@echo off
REM Kills any running WYSIWYG / WysiScan / XDevHubX processes so the installer
REM can overwrite them. Run this manually if an install is blocked by a
REM "file in use" / locked WYSIWYG.exe error, then launch INSTALL_WYSIWYG.exe.
REM /F = force, /T = kill the whole process tree (including child processes
REM like the scanner subprocess that can keep the EXE file handle locked).
taskkill /F /T /IM WYSIWYG.exe >nul 2>&1
taskkill /F /T /IM WysiScan.exe >nul 2>&1
taskkill /F /T /IM XDevHubX.exe >nul 2>&1
timeout /t 3 /nobreak >nul
taskkill /F /T /IM WYSIWYG.exe >nul 2>&1
timeout /t 2 /nobreak >nul

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