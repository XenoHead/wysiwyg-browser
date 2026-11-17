@echo off
rem Opens the WYSIWYG Patch Tool. Needs Python 3 with tkinter (already on PATH).
setlocal
cd /d "%~dp0.."
where pythonw >nul 2>&1
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3 or run patches\patch_gui.py yourself.
    pause
    exit /b 1
)
start "" pythonw "%~dp0patch_gui.py"
endlocal
exit /b 0
