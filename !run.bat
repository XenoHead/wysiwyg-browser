@echo off
REM !run.bat — Launch WYSIWYG main.py safely (PYTHONPATH cleared).
REM Optionally pre-clear stale processes first:
REM   Uncomment the next line to auto-kill stale processes before launch.
REM call C:\Git\WysiWyg-Browser\kill_stale_wysiwyg.py

set PYTHONPATH=
C:\Git\WysiWyg-Browser\.venv311\Scripts\python.exe main.py %*
