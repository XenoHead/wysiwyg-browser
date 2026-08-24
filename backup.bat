@echo off
REM ============================================================
REM  WYSIWYG-Browser — quick CODE backup (no compiled exe)
REM  Runs backup_code.py, which zips only source/code files into
REM  a timestamped zip: backups\WYSIWYG_backup_YYYY-MM-DD_HHMMSS.zip
REM  Includes the top-level code files + the Adds / WysiScan /
REM  WalmartSheet folders (code only: .py .spec .html .js .css
REM  .json .txt .md .bat .csv). Logs, db, images, exes, temp
REM  dirs are skipped, and locked files are skipped individually
REM  so a busy debug.log can never break the backup.
REM  Edit TOP_FILES / FOLDERS / INCLUDE in backup_code.py to
REM  change what gets backed up.
REM ============================================================
setlocal

set "PY=%~dp0.venv311\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "%~dp0backup_code.py"
if errorlevel 1 (
    echo  ERROR: backup failed.
    exit /b 1
)
endlocal
