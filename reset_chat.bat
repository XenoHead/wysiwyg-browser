@echo off
taskkill /F /T /IM Wysichat.exe >nul 2>&1
del /f /q "C:\FYRTOOLS\WysiChat\user_prefs_Scott.json" >nul 2>&1
del /f /q "C:\FYRTOOLS\WysiChat\wysichat_debug*" >nul 2>&1

echo WysiChat reset successful. Restarting now...
timeout /t 2 >nul

cd /d "C:\FYRTOOLS\WysiChat"
start "" "Wysichat.exe"