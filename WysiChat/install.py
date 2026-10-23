
import os
import time
import shutil
import winshell # You may need to pip install winshell and pypiwin32
from win32com.client import Dispatch

# Configuration
SOURCE_EXE = r"Z:\Tools\FYRTools\Wysichat\Wysichat.exe"
DEST_FOLDER = r"C:\FYRTOOLS\WysiChat"
SHORTCUT_NAME = "WysiChat.lnk"
SOURCE_SHORTCUT_DIR = r"\\192.168.0.108\FYRShare\Tools\FYRTools\WysiChat"

def install():
    try:
        # 0. Close application if running
        print("Closing any running instances...")
        os.system('taskkill /F /IM Wysichat.exe /T >nul 2>&1')
        time.sleep(2) # Give Windows a moment to release the file handle

        # 1. Create the local directory
        if not os.path.exists(DEST_FOLDER):
            os.makedirs(DEST_FOLDER)
            print(f"Created folder: {DEST_FOLDER}")

        # 2. Copy the executable
        dest_exe_path = os.path.join(DEST_FOLDER, "Wysichat.exe")
        shutil.copy2(SOURCE_EXE, dest_exe_path)
        print("Copying latest executable...")

        # 3. Create the Desktop Shortcut
        print("Copying Desktop Shortcut...")
        try:
            desktop = winshell.desktop()
            src_shortcut = os.path.join(SOURCE_SHORTCUT_DIR, SHORTCUT_NAME)
            dst_shortcut = os.path.join(desktop, SHORTCUT_NAME)
            shutil.copy2(src_shortcut, dst_shortcut)
            print("Installation complete! Shortcut copied to Desktop.")
        except Exception as e:
            print(f"Error copying desktop shortcut: {e}")

        # 4. Create Shortcut in Current User Startup (shell:startup)
        print("Adding to Current User Startup...")
        try:
            user_startup = winshell.startup()
            startup_shortcut_path = os.path.join(user_startup, SHORTCUT_NAME)
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(startup_shortcut_path)
            shortcut.Targetpath = dest_exe_path
            shortcut.WorkingDirectory = DEST_FOLDER
            shortcut.IconLocation = dest_exe_path
            shortcut.save()
            print(f"Successfully added to Startup: {user_startup}")
        except Exception as e:
            print(f"Error adding to Startup: {e}")
       
    except Exception as e:
        print(f"Error during installation: {e}")

if __name__ == "__main__":
    install() 