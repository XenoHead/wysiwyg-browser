@echo off
echo Installing PyInstaller...
pip install pyinstaller

echo.
echo Building UberPaste.exe...
pyinstaller --noconsole --onefile --name="UberPaste" --icon="UberPaste.ico" --clean UberPaste.py

echo.
echo Cleaning up build files...
rmdir /s /q build
del UberPaste.spec

echo.
echo Build complete! Your executable is in the "dist" folder.
pause