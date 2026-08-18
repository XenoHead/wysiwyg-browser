import PyInstaller.__main__
import os
import sys

def build_exe():
    # Ensure we are in the correct directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    script_name = os.path.join(base_dir, "scanner_server.py")
    exe_name = "WysiScan"
    icon_path = os.path.join(base_dir, "WysiScan.ico")

    # Define assets to bundle (source, destination inside EXE)
    # We place them in a 'WysiScan' folder inside the EXE to match scanner_server.py's ASSET_DIR logic
    assets = [
        ("scanner_test.html", "WysiScan"),
        ("WysiScan.ico", "WysiScan"),
        ("WysiScan.png", "WysiScan"),
    ]

    params = [
        script_name,
        "--onefile",
        "--noconsole",
        f"--name={exe_name}",
        f"--icon={icon_path}",
        "--hidden-import=tkinter",
        "--clean",
    ]

    # Add assets
    for src, dst in assets:
        full_src = os.path.join(base_dir, src)
        if os.path.exists(full_src):
            params.append(f"--add-data={full_src}{os.pathsep}{dst}")

    # Bundle config.json so the standalone behaves like the integrated version
    config_path = os.path.join(base_dir, "config.json")
    if os.path.exists(config_path):
        params.append(f"--add-data={config_path}{os.pathsep}.")

    PyInstaller.__main__.run(params)

if __name__ == "__main__":
    build_exe()