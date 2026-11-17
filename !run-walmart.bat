@ECHO OFF
SETLOCAL
CD /D "%~dp0"

REM ---------------------------------------------------------------------------
REM !run-walmart.bat - run the standalone Walmart API page (WalmartAPI/).
REM
REM This package is deliberately kept OUT of the main app: nothing here touches
REM main.py, WYSIWYG.spec or install.py, and nothing binds port 8008. It is safe
REM to run while the installed WYSIWYG is open.
REM
REM   !run-walmart.bat            start on 8009 and open the page
REM   !run-walmart.bat 8010       start on 8010 instead
REM   !run-walmart.bat -n         start without opening a browser
REM   !run-walmart.bat 8010 -n    both
REM
REM Credentials are read from .env in this folder. If the port is busy, uvicorn
REM says so ("error while attempting to bind on address") and this window stays
REM open on the PAUSE below.
REM ---------------------------------------------------------------------------

SET "PORT=8009"
SET "OPEN=--open"

IF /I "%~1"=="-n" SET "OPEN="
IF /I "%~1"=="-n" GOTO :haveargs
IF NOT "%~1"=="" SET "PORT=%~1"
IF /I "%~2"=="-n" SET "OPEN="
:haveargs

IF NOT EXIST ".venv311\Scripts\python.exe" GOTO :nopython
IF NOT EXIST "WalmartAPI\__main__.py" GOTO :nopackage

REM Do not inherit a PYTHONPATH that could shadow the package (same as !run.bat).
SET "PYTHONPATH="

ECHO ===============================================================
ECHO  WalmartAPI standalone  ^(not part of the main WYSIWYG app^)
ECHO  Page    http://127.0.0.1:%PORT%/walmart-api
ECHO  Docs    http://127.0.0.1:%PORT%/docs
ECHO  Lookup  POST /api/walmart-api/lookup
ECHO  Ctrl+C to stop.
ECHO ===============================================================
ECHO.

.\.venv311\Scripts\python.exe -m WalmartAPI --port %PORT% %OPEN%
IF ERRORLEVEL 1 GOTO :failed
EXIT /B 0

:nopython
ECHO ERROR: Python 3.11 environment not found ^(.venv311\Scripts\python.exe^).
ECHO        This project needs the 3.11 venv, not the default .venv.
GOTO :failed

:nopackage
ECHO ERROR: WalmartAPI\__main__.py not found - run this from the repo root.
GOTO :failed

:failed
ECHO.
ECHO !run-walmart.bat stopped.
PAUSE
EXIT /B 1
