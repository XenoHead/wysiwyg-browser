@ECHO OFF
CD /D "%~dp0"

IF NOT EXIST ".venv311\Scripts\python.exe" (
    ECHO ERROR: Python 3.11 build environment not found.
    EXIT /B 1
)
IF NOT EXIST "Conditions.json" (
    ECHO ERROR: Conditions.json not found.
    EXIT /B 1
)

rem Strip favorites from the source list before every build (dev editing can re-add them)
.\.venv311\Scripts\python.exe -c "import json,io;p=r'Conditions.json';d=json.load(io.open(p,encoding='utf-8'));[i.pop('favorite',None) for k,v in d.items() if isinstance(v,list) for i in v if isinstance(i,dict)];json.dump(d,io.open(p,'w',encoding='utf-8'),indent=4,ensure_ascii=False)"
IF ERRORLEVEL 1 EXIT /B %ERRORLEVEL%

ECHO.
ECHO [1/3] Cleaning up previous build folders...
IF EXIST "build" RMDIR /S /Q "build"
IF EXIST "dist" RMDIR /S /Q "dist"
rem WysiChat\dist also holds live chat_history_*.db / user_prefs_*.json / logs,
rem so ONLY its exe is deleted - never the folder. Removing the old exe first also
rem guarantees the "did the build produce an exe?" check below cannot pass on a
rem stale binary.
IF EXIST "WysiChat\build" RMDIR /S /Q "WysiChat\build"
IF EXIST "WysiChat\dist\Wysichat.exe" DEL /Q "WysiChat\dist\Wysichat.exe"

rem SET "SERVER_SHARE=\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\temp"

ECHO.
ECHO [2/3] Building Main Application (WYSIWYG.exe)...
:: Combined into single line to prevent batch file syntax errors
:: NOTE: must use the Python 3.11.15 venv (.venv311). The default .venv is Python 3.14,
:: which PyInstaller cannot freeze (pydantic_core fails to bundle on 3.14).
.\.venv311\Scripts\python.exe -m PyInstaller --noconfirm --onedir --windowed --icon="fyrlogo.ico" --add-data "app.js;." --add-data "fyrlogo.png;." --add-data "index.html;." --add-data "editor.html;." --add-data "admin.html;." --add-data "search.html;." --add-data "style_guide.html;." --add-data "data.json;." --add-data "colourmap.json;." --add-data "media_formats.json;." --add-data "version.json;." --add-data "changelog.txt;." --add-data "styles.css;." --add-data "colourrules.json;." --add-data "fyrlogo.ico;." --add-data "fyr-sign-front.png;." --add-data "Uberpaste;Uberpaste" --add-data "WysiScan;WysiScan" --add-data "Adds;Adds" --add-data "C:/Git/Xeno_ui;Xeno_ui" --name "WYSIWYG" --hidden-import=psutil --hidden-import=win32timezone --hidden-import=webview --hidden-import=cv2 --hidden-import=PIL --hidden-import=pyperclip --hidden-import=Xeno_ui.about --hidden-import=Xeno_ui.theme main.py
IF ERRORLEVEL 1 EXIT /B %ERRORLEVEL%
IF NOT EXIST "dist\WYSIWYG\WYSIWYG.exe" (
    ECHO ERROR: PyInstaller did not create dist\WYSIWYG\WYSIWYG.exe.
    EXIT /B 1
)
COPY /Y "Conditions.json" "dist\WYSIWYG\Conditions.json" >NUL
IF ERRORLEVEL 1 EXIT /B %ERRORLEVEL%
COPY /Y "colourmap.json" "dist\WYSIWYG\colourmap.json" >NUL
IF ERRORLEVEL 1 EXIT /B %ERRORLEVEL%

rem Shipped conditions list must never contain favorites
.\.venv311\Scripts\python.exe -c "import json,io;p=r'dist\WYSIWYG\Conditions.json';d=json.load(io.open(p,encoding='utf-8'));[i.pop('favorite',None) for k,v in d.items() if isinstance(v,list) for i in v if isinstance(i,dict)];json.dump(d,io.open(p,'w',encoding='utf-8'),indent=4,ensure_ascii=False)"
IF ERRORLEVEL 1 EXIT /B %ERRORLEVEL%

rem Credentials for the portable (un-installed) build
IF EXIST ".env" COPY /Y ".env" "dist\WYSIWYG\.env" >NUL
IF EXIST "keys.txt" COPY /Y "keys.txt" "dist\WYSIWYG\keys.txt" >NUL

rem Dev-only helpers must never ship
IF EXIST "dist\WYSIWYG\set_password.py" DEL /Q "dist\WYSIWYG\set_password.py"
IF EXIST "dist\WYSIWYG\hash_password.py" DEL /Q "dist\WYSIWYG\hash_password.py"

rem ---- Trim the bundled scanner ------------------------------------------
rem --add-data "WysiScan;WysiScan" copies the whole folder, which used to drag
rem ~300 MB of PyInstaller work dirs, old exes, scanner temp/scans, the
rem imageconvert virtualenv and logs into every install. None of that is used at
rem runtime, so strip it from the bundle before the installer runs.
SET "WKB=%CD%\dist\WYSIWYG\_internal\WysiScan"
FOR %%D IN (build dist dist_onefile temp scans __pycache__ .continuity .vscode AI-Memory) DO (
    IF EXIST "%WKB%\%%D" RMDIR /S /Q "%WKB%\%%D"
)
IF EXIST "%WKB%\imageconvert\.venvic" RMDIR /S /Q "%WKB%\imageconvert\.venvic"
FOR /D /R "%WKB%" %%P IN (__pycache__) DO @IF EXIST "%%P" RMDIR /S /Q "%%P"
FOR %%L IN (wysiscan_debug.log wysiscan_debug.log.1 _onefile_err.txt) DO (
    IF EXIST "%WKB%\%%L" DEL /Q "%WKB%\%%L"
)
ECHO Scanner payload trimmed.

rem ---- Drop Discogs Adds from the bundle ---------------------------------
rem Discogs Adds is not working and has no menu entry or hotkey any more, so its
rem files do not ship. Adds\ keeps the source; only the bundled copy is stripped.
SET "ADB=%CD%\dist\WYSIWYG\_internal\Adds"
FOR %%F IN (discogs_add.py discogs_add_page.html discogs_add_rules.json discogs_last_extract.json) DO (
    IF EXIST "%ADB%\%%F" DEL /Q "%ADB%\%%F"
)
FOR %%F IN ("%ADB%\Discogs ADD*.txt") DO @IF EXIST "%%~F" DEL /Q "%%~F"
FOR %%F IN ("%ADB%\__pycache__\discogs_add*.pyc") DO @IF EXIST "%%~F" DEL /Q "%%~F"
ECHO Discogs Adds payload removed.

ECHO.
ECHO [3/3] Building WysiChat (Wysichat.exe)...
rem Uses the chat's own venv when present (FreeSimpleGUI / cryptography live there),
rem otherwise the 3.11 build venv, otherwise whatever python is on PATH.
SET "CHATPY=%CD%\WysiChat\.venv\Scripts\python.exe"
IF NOT EXIST "%CHATPY%" SET "CHATPY=%CD%\.venv311\Scripts\python.exe"
IF NOT EXIST "%CHATPY%" SET "CHATPY=python"

PUSHD "WysiChat"
rem Per-user runtime files (chat_history_<alias>.db, user_prefs_<alias>.json,
rem machine_conf_<name>.json) must NEVER be added via --add-data: every install
rem creates its own next to the exe.
"%CHATPY%" -m PyInstaller --noconfirm --onefile --windowed --name "Wysichat" --icon "wysichat-logo.ico" --add-data "fyrlogo.png;." --add-data "fyrlogo_alert.png;." main.py
IF ERRORLEVEL 1 (
    POPD
    ECHO ERROR: Wysichat build failed. Close Wysichat.exe first if it is running.
    EXIT /B 1
)
POPD

IF NOT EXIST "WysiChat\dist\Wysichat.exe" (
    ECHO ERROR: PyInstaller did not create WysiChat\dist\Wysichat.exe.
    EXIT /B 1
)
ECHO WysiChat build OK: WysiChat\dist\Wysichat.exe

rem Ship the SAME run_me_Installer.bat next to INSTALL_WYSIWYG.exe, so the copy
rem in dist_install can never drift from the repo's version.
IF NOT EXIST "dist_install" MKDIR "dist_install"
COPY /Y "run_me_Installer.bat" "dist_install\run_me_Installer.bat" >NUL
ECHO run_me_Installer.bat refreshed in dist_install.

rem run_me_Installer.bat looks for close_local_chrome.ps1 NEXT TO ITSELF to close
rem the browser windows showing the local app before an install, so ship it too.
COPY /Y "close_local_chrome.ps1" "dist_install\close_local_chrome.ps1" >NUL
ECHO close_local_chrome.ps1 refreshed in dist_install.

rem The update check reads version.json from the folder the installer is published
rem to (\<server>\FYRShare\Tools\FYRTools\WYSIWYG), so keep the release number next
rem to the installer - a stale copy there means no machine sees the update banner.
COPY /Y "version.json" "dist_install\version.json" >NUL
ECHO version.json refreshed in dist_install.

rem IF EXIST ""%SERVER_SHARE%\WYSIWYG.exe" DEL /Q""
rem copy /Y "dist\WYSIWYG.exe" "%SERVER_SHARE%\"