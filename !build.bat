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
ECHO [1/2] Cleaning up previous build folders...
IF EXIST "build" RMDIR /S /Q "build"
IF EXIST "dist" RMDIR /S /Q "dist"

rem SET "SERVER_SHARE=\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\temp"

ECHO.
ECHO [2/2] Building Main Application (WYSIWYG.exe)...
:: Combined into single line to prevent batch file syntax errors
:: NOTE: must use the Python 3.11.15 venv (.venv311). The default .venv is Python 3.14,
:: which PyInstaller cannot freeze (pydantic_core fails to bundle on 3.14).
.\.venv311\Scripts\python.exe -m PyInstaller --noconfirm --onedir --windowed --icon="fyrlogo.ico" --add-data "app.js;." --add-data "fyrlogo.png;." --add-data "index.html;." --add-data "editor.html;." --add-data "admin.html;." --add-data "search.html;." --add-data "style_guide.html;." --add-data "data.json;." --add-data "media_formats.json;." --add-data "version.json;." --add-data "changelog.txt;." --add-data "styles.css;." --add-data "walmart.html;." --add-data "fyrlogo.ico;." --add-data "fyr-sign-front.png;." --add-data "Uberpaste;Uberpaste" --add-data "WysiScan;WysiScan" --add-data "WalmartSheet;WalmartSheet" --add-data "Adds;Adds" --add-data "C:/Git/Xeno_ui;Xeno_ui" --name "WYSIWYG" --hidden-import=psutil --hidden-import=win32timezone --hidden-import=webview --hidden-import=pytesseract --hidden-import=cv2 --hidden-import=PIL --hidden-import=pyperclip --hidden-import=Xeno_ui.about --hidden-import=Xeno_ui.theme main.py
IF ERRORLEVEL 1 EXIT /B %ERRORLEVEL%
IF NOT EXIST "dist\WYSIWYG\WYSIWYG.exe" (
    ECHO ERROR: PyInstaller did not create dist\WYSIWYG\WYSIWYG.exe.
    EXIT /B 1
)
COPY /Y "Conditions.json" "dist\WYSIWYG\Conditions.json" >NUL
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

rem IF EXIST ""%SERVER_SHARE%\WYSIWYG.exe" DEL /Q""
rem copy /Y "dist\WYSIWYG.exe" "%SERVER_SHARE%\"