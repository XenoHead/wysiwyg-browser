@echo off
echo [1/3] Verifying files...
echo.
echo [2/3] Cleaning old builds...
rem NEVER delete the dist folder: it also holds this machine's own chat data
rem (chat_history_<alias>.db, user_prefs_<alias>.json, machine_conf_<name>.json).
rem Only the previous exe and the PyInstaller scratch dir are removed.
if exist "dist\Wysichat.exe" del /q "dist\Wysichat.exe"
rmdir /s /q build 2>nul

echo [3/3] Building Wysichat.exe...
rem Those data files are created per user at runtime next to the exe - never pass
rem them to --add-data, or every user would inherit this machine's history.
pyinstaller --noconfirm --onefile --windowed --name "Wysichat" --icon "wysichat-logo.ico" --add-data "fyrlogo.png;." --add-data "fyrlogo_alert.png;." main.py


echo Syncing to local root...
copy /y "dist\Wysichat.exe" "Wysichat.exe"

echo Syncing to Z Drive...
copy /y "dist\Wysichat.exe" "Z:\Tools\FYRTools\Wysichat\Wysichat.exe"
copy /y "fyrlogo.png" "Z:\Tools\FYRTools\Wysichat\fyrlogo.png"
copy /y "fyrlogo.ico" "Z:\Tools\FYRTools\Wysichat\fyr-logo.ico"
copy /y "fyrlogo_alert.png" "Z:\Tools\FYRTools\Wysichat\fyrlogo_alert.png"

echo DONE!
pause