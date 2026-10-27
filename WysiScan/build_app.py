import PyInstaller.__main__
import os
import shutil
import stat
import time

# Ensure we are in the script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def remove_readonly(func, path, _):
    "Clear the readonly bit and reattempt the removal"
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        print(f"Failed to remove {path}: {e}")

# Cleanup previous build artifacts
print("Cleaning up previous build folders...")
for folder in ['build', 'dist']:
    if os.path.exists(folder):
        try:
            shutil.rmtree(folder, onerror=remove_readonly)
            print(f"Removed existing {folder} directory.")
        except Exception as e:
            print(f"Warning: Could not remove {folder}: {e}")
            print("Please ensure no other programs (like Explorer or a terminal) are using these folders.")

# Small delay to ensure filesystem catches up
time.sleep(1)

print("Building ScannerApp.exe...")

PyInstaller.__main__.run([
    'scanner_server.py',
    '--onefile',
    '--name=ScannerApp',
    '--add-data=scanner_test.html;.',  # Include the HTML file
    
    # Hidden imports often needed for uvicorn/fastapi/win32
    '--hidden-import=uvicorn.logging',
    '--hidden-import=uvicorn.loops',
    '--hidden-import=uvicorn.loops.auto',
    '--hidden-import=uvicorn.protocols',
    '--hidden-import=uvicorn.protocols.http',
    '--hidden-import=uvicorn.protocols.http.auto',
    '--hidden-import=uvicorn.lifespan',
    '--hidden-import=uvicorn.lifespan.on',
    '--hidden-import=win32timezone',
    '--hidden-import=pytesseract',
    '--hidden-import=PIL',
    '--hidden-import=PIL.Image',
    '--hidden-import=gemini_pool',
    '--paths=..',
    '--clean',
])

print("Build complete. Check the 'dist' folder.")