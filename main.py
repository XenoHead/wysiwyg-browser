import os
import sys
import tkinter
import tkinter.filedialog

# --- TKINTER DIALOG SUBPROCESS DISPATCHER ---
# This must stay at the very top of the file. When the EXE launches a subprocess 
# for a file dialog, we execute the script and exit immediately before the 
# FastAPI server or the process cleanup logic (which would kill the parent) starts.
if os.environ.get("WYSIWYG_DIALOG_MODE") == "true" or "--tkinter-dialog" in sys.argv:
    if "-c" in sys.argv:
        try:
            if hasattr(sys, '_MEIPASS'):
                sys.path.append(sys._MEIPASS)
            idx = sys.argv.index("-c")
            if idx + 1 < len(sys.argv):
                exec(sys.argv[idx + 1], globals())
        except Exception as e:
            print(f"Dialog execution error: {e}", file=sys.stderr)
    sys.exit(0)

import httpx
import socket
import shutil
import re
import json
import os
import sys
import signal
import subprocess
import threading
import time
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import psutil 
from datetime import datetime
from fastapi import FastAPI, Form, Body, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from html_format import format_discogs_to_html
from WalmartSheet.walmart import router as walmart_router


app = FastAPI()

# --- Extension Scrape Bridge ---
# In window mode this uses the PySide6 signal bridge. In browser mode we
# broadcast the requested URL to any open browser tabs over Server-Sent Events,
# so the active tab performs the scrape (no native window required).
try:
    from PySide6.QtCore import QObject, Signal
    class ScrapeBridge(QObject):
        trigger_scrape = Signal(str)
    scrape_bridge = ScrapeBridge()
except ImportError:
    scrape_bridge = None

# Browser-mode subscribers (open tabs listening via EventSource)
scrape_subscribers = set()

@app.post("/api/extension-scrape")
async def extension_scrape(data: dict = Body(...)):
    url = data.get("url")
    if not url:
        return {"status": "error", "message": "Missing URL"}
    # Notify every connected browser tab (browser mode)
    if scrape_subscribers:
        for q in list(scrape_subscribers):
            try:
                await q.put(url)
            except Exception:
                pass
        return {"status": "success"}
    # Fall back to the native PySide6 bridge (window mode)
    if scrape_bridge:
        scrape_bridge.trigger_scrape.emit(url)
        return {"status": "success"}
    return JSONResponse(status_code=503, content={"status": "error", "message": "No listener connected"})

@app.get("/api/extension-scrape/stream")
async def extension_scrape_stream():
    """SSE stream: pushes scrape URLs sent from the browser extension to this tab."""
    q = asyncio.Queue()
    scrape_subscribers.add(q)
    async def event_gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                url = await q.get()
                yield f"data: {json.dumps({'url': url})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            scrape_subscribers.discard(q)
    return StreamingResponse(event_gen(), media_type="text/event-stream")

# Track child processes to kill on shutdown
CHILD_PROCESSES = {}

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False):
        # --- FROZEN (PyInstaller) ---
        base_local = os.path.dirname(sys.executable)
        try:
            base_bundled = sys._MEIPASS # pyright: ignore[reportAttributeAccessIssue]
        except Exception:
            base_bundled = os.path.abspath(".")
            
        local_path = os.path.join(base_local, relative_path)
        bundled_path = os.path.join(base_bundled, relative_path)
        
        # Logic: Always prefer local file if it exists (allows user overrides/config)
        if os.path.exists(local_path):
            return local_path
        if os.path.exists(bundled_path):
            return bundled_path
        return local_path
    else:
        # --- DEV MODE ---
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
# Helper to mount static directories safely
def mount_static_dir(app_instance, folder_name, mount_path, name):
    path = resource_path(folder_name)
    if not os.path.exists(path):
        logging.warning(f"Static directory {folder_name} not found at {path}. Creating local fallback.")
        os.makedirs(path, exist_ok=True)
    app_instance.mount(mount_path, StaticFiles(directory=path), name=name)

mount_static_dir(app, "Uberpaste", "/UberPaste", "uberpaste_static")
mount_static_dir(app, "WysiScan", "/WysiScan", "wysiscan_static")
mount_static_dir(app, "WalmartSheet", "/WalmartSheet", "walmartsheet_static")

# Include Walmart Router
app.include_router(walmart_router)

def get_local_path(filename):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)

def init_cost_calc():
    path = get_local_path("cost_calc.json")
    if not os.path.exists(path):
        default = {"Cost_calulation": ["Like New", "Sealed", "VG+/Good", "VG+/Like New"]}
        with open(path, "w") as f:
            json.dump(default, f, indent=4)

def get_current_version_str():
    path = resource_path("version.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                v = json.load(f)
                return f"{v.get('major', 1)}.{v.get('minor', 0)}.{v.get('patch', 0)}.{v.get('build', 0)}"
        except:
            pass
    return "1.2.0.0"

DISCOGS_TOKEN = "PzJscAOAJKspsQFlsvQTDChKjbnaWypCetHnoyGK" 
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "PzJscAOAJKspsQFlsvQTDChKjbnaWypCetHnoyGK")
# Load version dynamically for User-Agent
HEADERS = {"User-Agent": f"WYSIWYG/{get_current_version_str()}", "Authorization": f"Discogs token={DISCOGS_TOKEN}"}
CHANGELOG_FILE = "changelog.txt"
HISTORY_FILE = "wysiwyg_history.json"
WALMART_CONTEXT_CACHE_FILE = "walmart_context_cache.json"
LAST_HEARTBEAT = time.time()

def init_conditions():
    local_path = get_local_path("Conditions.json")
    server_path = r"\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\Conditions.json"
    
    if not os.path.exists(local_path):
        if os.path.exists(server_path):
            try:
                shutil.copy2(server_path, local_path)
                print("Conditions.json initialized from server.")
            except Exception as e:
                print(f"Failed to copy Conditions.json from server: {e}")
        else:
            # Create default if server also unavailable
            default = {"lp": [], "cd": [], "cassette": []}
            try:
                with open(local_path, "w") as f:
                    json.dump(default, f, indent=4)
                print("Conditions.json initialized with defaults.")
            except: pass

POSSIBLE_ROOTS = [
    r"Z:\Tools\FYRTools",
    r"\\BATMAN\SupergirlNew\Tools\FYRTools"
]
def resolve_server_paths():
    for path in POSSIBLE_ROOTS:
        if os.path.exists(path): 
            return path, os.path.join(path, "WYSIWYG")
    return r"Z:\Tools\FYRTools", r"Z:\Tools\FYRTools\WYSIWYG"

SERVER_ROOT, WYSIWYG_SERVER_DIR = resolve_server_paths()
SERVER_VERSION_PATH = os.path.join(WYSIWYG_SERVER_DIR, "version.json")
SERVER_EXE_PATH = os.path.join(WYSIWYG_SERVER_DIR, "WYSIWYG.exe")
INSTALLER_PATH = os.path.join(WYSIWYG_SERVER_DIR, "INSTALL_WYSIWYG.exe")


def load_json_data(filename):
    path = resource_path(filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None

def save_to_history(entry):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f: history = json.load(f)
        except: history = []
    if not any(item.get('url') == entry['url'] for item in history):
        history.insert(0, entry)
        with open(HISTORY_FILE, "w") as f: json.dump(history[:20], f, indent=4)

# --- VERSION ENDPOINTS ---
@app.get("/api/version")
async def get_version_endpoint():
    path = resource_path("version.json")
    local_version = {"major": 1, "minor": 2, "patch": 0, "build": 0}
    
    if os.path.exists(path):
        try:
            with open(path, "r") as f: local_version = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load local version.json: {e}")
        
    # Check Server Version
    update_available = False
    server_ver_obj = None
    try:
        if os.path.exists(SERVER_VERSION_PATH):
            with open(SERVER_VERSION_PATH, "r") as f:
                server_version = json.load(f)
                
                l_ver = (int(local_version.get("major", 0)), int(local_version.get("minor", 0)), int(local_version.get("patch", 0)), int(local_version.get("build", 0)))
                s_ver = (int(server_version.get("major", 0)), int(server_version.get("minor", 0)), int(server_version.get("patch", 0)), int(server_version.get("build", 0)))
                
                if s_ver > l_ver:
                    update_available = True
                server_ver_obj = server_version
        else:
            logging.info(f"Server version file not found, cannot check for updates. Path: {SERVER_VERSION_PATH}")

    except Exception as e:
        logging.error(f"Error checking server version: {e}")
        
    local_version["update_available"] = update_available
    if server_ver_obj:
        local_version["server_version"] = server_ver_obj
    return local_version

@app.get("/api/changelog")
async def get_changelog_endpoint():
    path = resource_path(CHANGELOG_FILE)
    if not os.path.exists(path):
        return {"entries": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Split by "### " which we use as delimiter
        raw_entries = content.split("### ")
        entries = []
        for raw in raw_entries:
            if not raw.strip(): continue
            entries.append("### " + raw.strip())
        return {"entries": entries[-3:][::-1]} # Return last 3, reversed (newest first)
    except:
        return {"entries": []}

@app.post("/api/version")
async def update_version_endpoint(data: dict = Body(...)):
    path = get_local_path("version.json")
    try:
        new_version = {
            "major": int(data.get("major", 0)),
            "minor": int(data.get("minor", 0)),
            "patch": int(data.get("patch", 0)),
            "build": int(data.get("build", 0))
        }
        with open(path, "w") as f: json.dump(new_version, f, indent=4)
        
        # Handle Changelog
        cl_text = data.get("changelog", "").strip()
        if cl_text:
            changelog_path = get_local_path(CHANGELOG_FILE)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            v_str = f"v{new_version['major']}.{new_version['minor']}.{new_version['patch']}.{new_version['build']}"
            entry = f"\n### {v_str} - {timestamp}\n{cl_text}\n"
            with open(changelog_path, "a", encoding="utf-8") as f: f.write(entry)
            
        return {"status": "success", "version": new_version}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/open-listings-folder")
async def open_listings_folder_endpoint():
    listings_dir = get_local_path("Listings")
    if not os.path.exists(listings_dir):
        os.makedirs(listings_dir)
        
    # Try to open today's file first
    filename = datetime.now().strftime("%Y-%m-%d") + "_Listings.txt"
    file_path = os.path.join(listings_dir, filename)
    
    try:
        if os.path.exists(file_path):
            os.startfile(file_path)
        else:
            os.startfile(listings_dir)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/open-update-folder")
async def open_update_folder_endpoint():
    _, folder_path = resolve_server_paths()
    try:
        if os.path.exists(folder_path):
            os.startfile(folder_path)
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"status": "error", "message": "Folder not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/push-version")
async def push_version_endpoint():
    _, server_dir = resolve_server_paths()
    files = ["version.json", "changelog.txt"]
    
    if not os.path.exists(server_dir):
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Server directory not found. Tried accessing: {server_dir}"})

    try:
        copied_files = []
        for filename in files:
            local_path = get_local_path(filename)
            server_path = os.path.join(server_dir, filename)
            
            if os.path.exists(local_path):
                shutil.copy2(local_path, server_path)
                copied_files.append(filename)
        
        if not copied_files:
             return JSONResponse(status_code=404, content={"status": "error", "message": "No local version files found to push."})

        return {"status": "success", "message": f"Pushed to server: {', '.join(copied_files)}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/view-requests")
async def view_requests_endpoint():
    root_dir, _ = resolve_server_paths()
    file_path = os.path.join(root_dir, "Feature Requests", "requests.txt")
    
    if not os.path.exists(file_path):
        return {"status": "error", "message": "Requests file not found on server."}
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/run-installer")
async def run_installer_endpoint():
    try:
        if os.path.exists(INSTALLER_PATH):
            import tempfile
            bat_path = os.path.join(tempfile.gettempdir(), "update_wysiwyg.bat")
            
            # Write a batch file that kills the running processes and then launches the installer.
            # This completely decouples the installer process from the parent process handle inheritance.
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(f'@echo off\n'
                        f'timeout /t 1 /nobreak >nul\n'
                        f'taskkill /F /IM WYSIWYG.exe\n'
                        f'taskkill /F /IM WysiScan.exe\n'
                        f'taskkill /F /IM XDevHubX.exe\n'
                        f'timeout /t 1 /nobreak >nul\n'
                        f'start "" "{INSTALLER_PATH}"\n'
                        f'exit\n')
            
            os.startfile(bat_path)
            return {"status": "success"}
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Installer not found at {INSTALLER_PATH}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/run-uberpaste")
async def run_uberpaste_endpoint():
    # Check if UberPaste is already running by iterating through processes
    for p in psutil.process_iter(['cmdline']):
        try:
            if p.info['cmdline']:
                cmd_str = ' '.join(p.info['cmdline'])
                if 'UberPaste.py' in cmd_str or '--uberpaste' in cmd_str:
                    logging.info("UberPaste process found, not starting a new one.")
                    return {"status": "success", "message": "UberPaste is already running."}
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass # Process ended before we could inspect it

    try:
        if getattr(sys, 'frozen', False):
            # Running as compiled EXE: Dispatch to self with flag
            subprocess.Popen([sys.executable, "--uberpaste"])
        else:
            # Running as script
            uberpaste_script_path = resource_path(os.path.join("Uberpaste", "UberPaste.py"))
            python_executable = sys.executable

            if not os.path.exists(uberpaste_script_path):
                logging.error(f"UberPaste script not found at {uberpaste_script_path}")
                return JSONResponse(status_code=404, content={"status": "error", "message": "UberPaste script not found."})

            # Use Popen to run the script in a new, non-blocking process.
            # We no longer track it as a child process to be killed on shutdown.
            subprocess.Popen([python_executable, uberpaste_script_path])

        return {"status": "success", "message": "UberPaste launched."}
    except Exception as e:
        logging.error(f"Failed to launch UberPaste: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/run-wysiscan")
async def run_wysiscan_endpoint():
    try:
        # Standardized port for WysiScan (8010)
        target_port = 8010
        if is_port_in_use(target_port):
            logging.info(f"WysiScan server is already running on port {target_port}.")
            return {"status": "success", "message": "WysiScan is already running."}

        if getattr(sys, 'frozen', False):
            # Running as compiled EXE: Dispatch to self with flag
            proc = subprocess.Popen([sys.executable, "--wysiscan", "--launched-by-main"])
        else:
            # Running as script
            wysiscan_script_path = resource_path(os.path.join("WysiScan", "scanner_server.py"))
            python_executable = sys.executable

            if not os.path.exists(wysiscan_script_path):
                logging.error(f"WysiScan script not found at {wysiscan_script_path}")
                return JSONResponse(status_code=404, content={"status": "error", "message": "WysiScan script not found."})

            # Use Popen to run the script in a new, non-blocking process
            # Pass an argument to prevent it from opening its own browser window
            proc = subprocess.Popen([python_executable, wysiscan_script_path, "--launched-by-main"])
            
        CHILD_PROCESSES["wysiscan"] = proc
        
        time.sleep(2.0) # Give the server a moment to start
        return {"status": "success", "message": "WysiScan launched."}
    except Exception as e:
        logging.error(f"Failed to launch WysiScan: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/history-list")
async def get_history_list():
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        except:
            history = []
    
    # Enforce 20 item limit on load to prevent bloat
    if len(history) > 20:
        history = history[:20]
        with open(HISTORY_FILE, "w") as f: json.dump(history, f, indent=4)

    html = '<button hx-post="/clear-history" hx-target="#historyList" style="margin-bottom:10px; background:#dc3545; color:white; border:none; padding:5px; border-radius:4px; cursor:pointer; font-size:11px; width:100%;">Clear History</button>'

    if not history:
        return HTMLResponse(html + "<p style='font-size:12px; color:#666;'>No history yet.</p>")
    
    html += '<div style="display:flex; flex-direction:column; gap:8px;">'
    for entry in history:
        # We escape the text to prevent JSON/HTML breakage
        safe_text = entry.get('raw_text', '').replace('"', '&quot;').replace('`', '\\`').replace('\n', '\\n')
        html += f"""
            <div style="background:white; padding:8px; border-radius:4px; border:1px solid #ccc; cursor:pointer;"
                 onclick="loadHistoryItem(`{safe_text}`)">
                <div style="font-weight:bold; font-size:11px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{entry['title']}</div>
            </div>
        """
    html += '</div>'
    return HTMLResponse(html)

@app.post("/clear-history")
async def clear_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
    return HTMLResponse("<p style='font-size:12px; color:#666;'>History cleared.</p>")
    
@app.get("/settings")
async def get_settings():
    data = load_json_data("data.json")
    if data is None:
        return {"Condition of Media": [], "Format Tags": [], "Edition": []}
    return data

@app.post("/save-settings")
async def save_settings(new_data: dict = Body(...)):
    local_path = get_local_path("data.json")
    try:
        with open(local_path, "w") as f:
            json.dump(new_data, f, indent=4)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/update-menus")
async def update_menus():
    _, base_server_path = resolve_server_paths()
    files = ["data.json", "version.json", "changelog.txt"]
    updated = []
    
    try:
        if not os.path.exists(base_server_path):
            return JSONResponse(status_code=404, content={"status": "error", "message": "Server path not found."})
            
        # Check if server version is older
        server_v_path = os.path.join(base_server_path, "version.json")
        local_v_path = resource_path("version.json")
        
        if os.path.exists(server_v_path):
            try:
                with open(server_v_path, "r") as f: sv = json.load(f)
                
                lv = {"major": 0, "minor": 0, "patch": 0}
                if os.path.exists(local_v_path):
                    with open(local_v_path, "r") as f: lv = json.load(f)
                
                s_tuple = (int(sv.get("major", 0)), int(sv.get("minor", 0)), int(sv.get("patch", 0)), int(sv.get("build", 0)))
                l_tuple = (int(lv.get("major", 0)), int(lv.get("minor", 0)), int(lv.get("patch", 0)), int(lv.get("build", 0)))
                
                if s_tuple < l_tuple:
                    msg = f"Server version ({s_tuple[0]}.{s_tuple[1]}.{s_tuple[2]}) is older than local ({l_tuple[0]}.{l_tuple[1]}.{l_tuple[2]}). Update aborted."
                    return JSONResponse(content={"status": "error", "message": msg})
            except: pass

        for filename in files:
            server_path = os.path.join(base_server_path, filename)
            local_path = get_local_path(filename)
            if os.path.exists(server_path):
                shutil.copy2(server_path, local_path)
                updated.append(filename)
                
        if not updated:
            return JSONResponse(status_code=404, content={"status": "error", "message": "No files found on server."})
            
        return {"status": "success", "message": f"Updated from server: {', '.join(updated)}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/upload-menus")
async def upload_menus():
    _, server_dir = resolve_server_paths()
    server_path = os.path.join(server_dir, "data.json")
    local_path = get_local_path("data.json")

    try:
        if not os.path.exists(local_path):
            return JSONResponse(status_code=404, content={"status": "error", "message": "Local data.json not found."})
            
        if os.path.exists(server_path):
            backup = server_path + ".old"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(server_path, backup)
            
        shutil.copy2(local_path, server_path)
        return {"status": "success", "message": "Menus uploaded to server."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/submit-request")
async def submit_request(data: dict = Body(...)):
    name = data.get("name", "Anonymous")
    request_text = data.get("request", "")
    
    if not request_text:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Request cannot be empty."})
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] Name: {name}\nRequest: {request_text}\n{'-'*50}\n"
    
    root_dir, _ = resolve_server_paths()
    file_path = os.path.join(root_dir, "Feature Requests", "requests.txt")
    
    try:
        # Ensure directory exists if possible
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(entry)
        return {"status": "success", "message": "Request submitted successfully."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/get-requests-json")
async def get_requests_json():
    try:
        root_dir, _ = resolve_server_paths()
        file_path = os.path.join(root_dir, "Feature Requests", "requests.txt")
        
        if not os.path.exists(file_path):
            return []
    except Exception as e:
        return [{"error": f"Path Access Error: {str(e)}"}]
    
    requests_list = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Split by separator used in submit_request
        raw_entries = content.split("-" * 50)
        
        for i, entry in enumerate(raw_entries):
            if not entry.strip(): continue
            
            # Simple parsing
            lines = entry.strip().split('\n')
            timestamp = ""
            name = ""
            req_text = ""
            
            for line in lines:
                if line.startswith("[") and "] Name:" in line:
                    parts = line.split("] Name:", 1)
                    timestamp = parts[0].strip("[")
                    name = parts[1].strip()
                elif line.startswith("Request:"):
                    req_text = line.split("Request:", 1)[1].strip()
                else:
                    if req_text:
                        req_text += "\n" + line.strip()
            
            if req_text:
                requests_list.append({
                    "id": i,
                    "timestamp": timestamp,
                    "name": name,
                    "request": req_text
                })
                
        return requests_list
    except Exception as e:
        return [{"error": str(e)}]

@app.post("/api/resolve-request")
async def resolve_request(data: dict = Body(...)):
    req_id = int(data.get("id", -1))
    if req_id < 0:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid ID"})

    root_dir, _ = resolve_server_paths()
    file_path = os.path.join(root_dir, "Feature Requests", "requests.txt")
    
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"status": "error", "message": "Requests file not found"})

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        raw_entries = content.split("-" * 50)
        valid_entries = [e for e in raw_entries if e.strip()]
        
        if req_id >= len(valid_entries):
             return JSONResponse(status_code=404, content={"status": "error", "message": "Request ID not found"})
        
        # Extract text for changelog before deleting
        resolved_entry_raw = valid_entries[req_id]
        req_text_match = re.search(r'Request:(.*)', resolved_entry_raw, re.DOTALL)
        req_text = req_text_match.group(1).strip() if req_text_match else "Unknown Request"

        # Remove and Save
        valid_entries.pop(req_id)
        new_content = ""
        for e in valid_entries:
            new_content += e.strip() + "\n" + ("-" * 50) + "\n"
            
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        # Update Changelog
        changelog_path = get_local_path(CHANGELOG_FILE)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"\n### Resolved Request - {timestamp}\n-- Resolved: {req_text}\n"
        
        with open(changelog_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
            
        return {"status": "success", "message": "Request resolved and added to changelog."}
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/ready")
async def get_ready_status():
    """Endpoint to check if the FastAPI server is ready."""
    return {"status": "ready"}

@app.get("/")
async def serve_index(): 
    return FileResponse(resource_path("index.html"))

@app.get("/editor")
async def serve_editor():
    return FileResponse(resource_path("editor.html"))

@app.get("/admin")
async def serve_admin():
    path = resource_path("admin.html")
    if not os.path.exists(path):
        return HTMLResponse(f"<h1>Error: admin.html not found</h1><p>Expected location: {path}</p>", status_code=404)
    return FileResponse(path)

# Walmart routes moved to WalmartSheet/walmart.py

@app.post("/api/scrape-json")
async def scrape_discogs_json(data: dict = Body(...)):
    url = data.get("url")
    if not url:
        return JSONResponse(status_code=400, content={"status": "error", "message": "URL is required."})

    release_id = None
    is_master = False
    listing_data = None

    match = re.search(r'release/(\d+)', url)
    if match:
        release_id = match.group(1)

    async with httpx.AsyncClient() as client:
        if not release_id:
            match_listing = re.search(r'(?:sell|shop)/item/(\d+)', url)
            if match_listing:
                try:
                    l_resp = await client.get(f"https://api.discogs.com/marketplace/listings/{match_listing.group(1)}", headers=HEADERS)
                    if l_resp.status_code == 200:
                        listing_data = l_resp.json()
                        release_id = str(listing_data.get('release', {}).get('id', ''))
                except Exception:
                    pass # Ignore listing errors and proceed

            if not release_id:
                match_master = re.search(r'master/(\d+)', url)
                if match_master:
                    m_resp = await client.get(f"https://api.discogs.com/masters/{match_master.group(1)}", headers=HEADERS)
                    if m_resp.status_code == 200:
                        release_id = str(m_resp.json().get('main_release', ''))
                        is_master = True

        if not release_id:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid URL. Must be a Release, Master, or Marketplace Item link."})

        try:
            resp = await client.get(f"https://api.discogs.com/releases/{release_id}", headers=HEADERS)
            if resp.status_code != 200:
                error_message = f"Discogs API Error: Status {resp.status_code}"
                return JSONResponse(status_code=resp.status_code, content={"status": "error", "message": error_message})

            release_data = resp.json()

            response_payload = {
                "release": release_data,
                "listing": listing_data,
                "is_master": is_master
            }

            return JSONResponse(content={"status": "success", "data": response_payload})

        except Exception as e:
            logging.error(f"Scrape JSON Error: {e}", exc_info=True)
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# Walmart Logic Moved to WalmartSheet/walmart.py

@app.get("/search")
async def serve_search():
    return FileResponse(resource_path("search.html"))

@app.get("/fyrlogo.png")
async def serve_logo():
    return FileResponse(resource_path("fyrlogo.png"))

@app.get("/fyrglogo.png")
async def serve_logo_typo():
    return FileResponse(resource_path("fyrlogo.png"))

@app.get("/wysiwyglogo.png")
async def serve_logo_wysiwyg():
    return FileResponse(resource_path("fyrlogo.png"))

@app.get("/styles.css")
async def serve_css():
    return FileResponse(resource_path("styles.css"))

@app.get("/app.js")
async def serve_js():
    return FileResponse(resource_path("app.js"))

@app.get("/style-guide")
async def serve_style_guide():
    return FileResponse(resource_path("style_guide.html"))

@app.post("/save-css")
async def save_css_endpoint(data: dict = Body(...)):
    css_content = data.get("css", "")
    if not css_content:
        return JSONResponse(status_code=400, content={"status": "error", "message": "No CSS content provided"})
    
    local_path = get_local_path("styles.css")
    try:
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(css_content)
        return {"status": "success", "message": "CSS saved successfully"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/allpass.json")
async def get_password_file():
    file_path = get_local_path("allpass.json")
    
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return Response(status_code=404)

@app.get("/api/variable-conditions")
async def get_variable_conditions():
    """Return the saved MEDIA CONDITION variable conditions from allpass.json.
    Returns 404 if the admin file is not present (feature disabled)."""
    file_path = get_local_path("allpass.json")
    if not os.path.exists(file_path):
        return Response(status_code=404)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            "media_condition": data.get("media_condition", ""),
            "is_oop": data.get("is_oop", False)
        }
    except Exception:
        return {"media_condition": "", "is_oop": False}

@app.post("/api/save-variable-conditions")
async def save_variable_conditions(data: dict = Body(...)):
    """Persist MEDIA CONDITION variable conditions into allpass.json.
    Only works when the admin file is present."""
    file_path = get_local_path("allpass.json")
    if not os.path.exists(file_path):
        return JSONResponse(status_code=403, content={"status": "error", "message": "Admin file not present"})
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    existing["media_condition"] = data.get("media_condition", "")
    existing["is_oop"] = bool(data.get("is_oop", False))
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/media_formats.json")
async def get_media_formats():
    file_path = resource_path("media_formats.json")
    
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return Response(status_code=404)

@app.get("/api/cost_calc.json")
async def get_cost_calc():
    file_path = resource_path("cost_calc.json")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return Response(status_code=404)

@app.get("/api/conditions")
async def get_conditions(master: bool = False):
    if master:
        server_path = r"\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\Conditions.json"
        if os.path.exists(server_path):
            return FileResponse(server_path)
        return {"cassette": [], "cd": [], "lp": []}
    
    file_path = get_local_path("Conditions.json")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    # Return empty default if file missing
    return {"cassette": [], "cd": [], "lp": []}

@app.post("/api/save-conditions")
async def save_conditions(data: dict = Body(...), master: bool = False):
    if master:
        server_path = r"\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\Conditions.json"
        try:
            with open(server_path, "w") as f:
                json.dump(data, f, indent=4)
            return {"status": "success", "message": "Master file updated on server."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to save to server: {e}"}

    file_path = get_local_path("Conditions.json")
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/admin/sync-conditions")
async def sync_conditions(data: dict = Body(...)):
    # User requested this admin edit screen should NOT edit local, only server.
    server_path = r"\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\Conditions.json"
    try:
        with open(server_path, "w") as f:
            json.dump(data, f, indent=4)
        return {"status": "success", "message": "Master file updated on server."}
    except Exception as e:
        return {"status": "error", "message": f"Server update failed: {e}"}

@app.post("/api/merge-conditions")
async def merge_conditions():
    local_path = get_local_path("Conditions.json")
    server_path = r"\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\Conditions.json"
    
    local_data = {"lp": [], "cd": [], "cassette": []}
    if os.path.exists(local_path):
        try:
            with open(local_path, "r") as f: local_data = json.load(f)
        except: pass
        
    server_data = {"lp": [], "cd": [], "cassette": []}
    if os.path.exists(server_path):
        try:
            with open(server_path, "r") as f: server_data = json.load(f)
        except: 
            return {"status": "error", "message": "Could not read master file on server."}
    else:
        return {"status": "error", "message": "Server master file not found."}

    # Merge logic
    merged_data = {}
    for cat in ["lp", "cd", "cassette"]:
        local_list = local_data.get(cat, [])
        server_list = server_data.get(cat, [])
        
        # Use a dict keyed by title to handle merging
        combined = {}
        # Load server first, then local (so if same title, local wins? or server wins?)
        # User said: "gets the changes made by an admin, but dose not loose any of the items they manually added"
        # If admin changed the TEXT of a title the user also has, admin's text is probably "the change".
        # But if the user customized it, maybe they want theirs.
        # Usually, "Admin changes" take precedence for the same title.
        for item in local_list:
            if item.get("title"): combined[item["title"]] = item
            
        for item in server_list:
            if item.get("title"): combined[item["title"]] = item
            
        # Convert back to list and sort
        final_list = list(combined.values())
        final_list.sort(key=lambda x: x.get("title", "").lower())
        merged_data[cat] = final_list

    # Save locally
    try:
        with open(local_path, "w") as f:
            json.dump(merged_data, f, indent=4)
        return {"status": "success", "message": "Conditions merged with server updates.", "data": merged_data}
    except Exception as e:
        return {"status": "error", "message": f"Merge failed: {e}"}


@app.get("/heartbeat")
async def heartbeat():
    global LAST_HEARTBEAT
    LAST_HEARTBEAT = time.time()
    return {"status": "ok"}

@app.exception_handler(Exception)
async def validation_exception_handler(request: Request, exc: Exception):
    # This is a global catch-all to prevent "Internal Server Error" HTML responses
    # from breaking the frontend which expects JSON.
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"An unexpected server error occurred: {exc}"},
    )

@app.post("/format-html")
async def format_html_route(raw_text: str = Form(None)):
    try:
        if not raw_text or raw_text.strip() == "":
            return Response(content="No tracklist data found.", media_type="text/plain")
            
        # Filter out time durations from the Tracklist section
        lines = raw_text.split('\n')
        cleaned_lines = []
        in_tracklist = False
        for line in lines:
            if "Tracklist" in line:
                in_tracklist = True
            
            if in_tracklist:
                line = re.sub(r'\s+\d{1,2}:\d{2}$', '', line.rstrip())
            
            cleaned_lines.append(line)
        
        raw_text = "\n".join(cleaned_lines)

        # This calls your logic in html_format.py
        formatted_html = format_discogs_to_html(raw_text)
        
        # Return raw text so it fills the textarea correctly
        return Response(content=formatted_html, media_type="text/plain")
        
    except Exception as e:
        return Response(content=f"Error: {str(e)}", media_type="text/plain")
        

@app.post("/scrape")
async def scrape_discogs(url: str = Form(...)):
    release_id = None 
    is_master = False
    from_marketplace = False
    match = re.search(r'release/(\d+)', url)
    if match: release_id = match.group(1)

    async with httpx.AsyncClient() as client:
        if not release_id:
            # Check for Marketplace Item URL (sell/item/12345 or shop/item/12345)
            match_listing = re.search(r'(?:sell|shop)/item/(\d+)', url)
            if match_listing:
                from_marketplace = True
                l_resp = await client.get(f"https://api.discogs.com/marketplace/listings/{match_listing.group(1)}", headers=HEADERS)
                if l_resp.status_code == 200: 
                    release_id = str(l_resp.json().get('release', {}).get('id', ''))
            
            # Check for Master Release URL (master/12345)
            if not release_id:
                match_master = re.search(r'master/(\d+)', url)
                if match_master:
                    m_resp = await client.get(f"https://api.discogs.com/masters/{match_master.group(1)}", headers=HEADERS)
                    if m_resp.status_code == 200:
                        release_id = str(m_resp.json().get('main_release', ''))
                        is_master = True
        
        if not release_id: return HTMLResponse("<span style='color:red;'>Invalid URL. Must be a Release, Master, or Marketplace Item link.</span>")

        try: 
            resp = await client.get(f"https://api.discogs.com/releases/{release_id}", headers=HEADERS)
            if resp.status_code != 200:
                error_message = f"Discogs API returned status code: {resp.status_code}."
                if resp.status_code == 404:
                    if from_marketplace:
                        error_message = "Error 404 (Not Found). This marketplace listing appears to be linked to a 'Draft' release. Draft releases are not accessible via the Discogs API, so this item cannot be scraped automatically."
                    else:
                        error_message = "Error 404 (Not Found). The release ID may be incorrect, the page removed, or it could be a draft release which is not accessible via the API."
                elif resp.status_code == 401:
                    error_message = "Error 401 (Unauthorized). The Discogs API token may be invalid or expired."
                elif resp.status_code == 429:
                    error_message = "Error 429 (Too Many Requests). We're making too many requests to Discogs. Please wait a minute before trying again."
                
                return HTMLResponse(f"""
                    <div style="background:#ffebee; border:1px solid #c62828; color:#c62828; padding:10px; border-radius:4px;">
                        <strong style="font-size:12px;">Scrape Failed</strong>
                        <p style="margin:5px 0 0 0; font-size:11px;">{error_message}</p>
                    </div>
                """)
            data = resp.json()
            artist_str = ""
            for a in data.get('artists', []):
                name = a.get('anv') or a.get('name') or 'Unknown'
                name = re.sub(r'\s*\(\d+\)$', '', name).strip()
                artist_str += name
                if a.get('join'):
                    j = a.get('join').strip()
                    if j == ',': artist_str += ', '
                    else: artist_str += f" {j} "
            artist = artist_str.strip() if artist_str else re.sub(r'\s*\(\d+\)$', '', data.get('artists_sort', 'Unknown')).strip()
            album = data.get('title', 'Unknown')
            

            labels_data = data.get('labels') or []
            
            # 1. Clean and Collect
            temp_labels = []
            for l in labels_data:
                name = l.get('name', 'N/A')
                cat = l.get('catno', 'N/A')
                
                name = name.replace('*', '')
                name = re.sub(r'\s*\(\d+\)', '', name)
                name = re.sub(r'Not On Label.*', '', name, flags=re.IGNORECASE).strip()
                if name.upper() == "N/A":
                    name = ""
                
                cat = str(cat).strip() if cat is not None else ""
                if cat.lower() == "none" or cat == "":
                    cat = ""
                
                if name or cat:
                    temp_labels.append({"name": name, "cat": cat})

            # --- Label Formatting Logic ---
            cat_counts = {}
            for item in temp_labels:
                cat = item.get('cat')
                if cat:
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1

            has_shared_cat = any(count > 1 for count in cat_counts.values())
            has_multiple_distinct_cats = len(cat_counts) > 1
            is_complex_case = has_shared_cat and has_multiple_distinct_cats

            if is_complex_case:
                # New logic for releases with multiple labels sharing a cat#, alongside other labels with their own cat#
                grouped_by_cat = {}
                cat_order = []
                for item in temp_labels:
                    cat_key = item.get('cat')
                    if not cat_key: cat_key = 'N/A' # Group labels without cat# together
                    
                    if cat_key not in grouped_by_cat:
                        grouped_by_cat[cat_key] = []
                        cat_order.append(cat_key)
                    grouped_by_cat[cat_key].append(item['name'])

                parts = []
                for cat in cat_order:
                    # Deduplicate names while preserving order of first appearance
                    unique_names = []
                    for n in grouped_by_cat[cat]:
                        if n not in unique_names:
                            unique_names.append(n)
                    names_str = " / ".join(unique_names)
                    
                    if cat == 'N/A':
                        parts.append(names_str)
                    else:
                        parts.append(f"{names_str} {cat}".strip())
                
                label_str = f"Label: {' - '.join(parts)}"
            else:
                # Original logic for all other cases
                grouped_labels = []
                for item in temp_labels:
                    found = False
                    for group in grouped_labels:
                        if group['name'] == item['name']:
                            found = True
                            if item['cat'] and item['cat'] not in group['cats']:
                                group['cats'].append(item['cat'])
                            break
                    if not found:
                        new_group = {'name': item['name'], 'cats': []}
                        if item['cat']:
                            new_group['cats'].append(item['cat'])
                        grouped_labels.append(new_group)

                if not grouped_labels:
                    label_str = "Label: "
                else:
                    is_shared = False
                    shared_cats_str = ""

                    if len(grouped_labels) > 1:
                        first_group_cats = grouped_labels[0]['cats']
                        all_match = True
                        if not first_group_cats: # If first group has no cat#, it can't match
                            all_match = False
                        else:
                            for group in grouped_labels[1:]:
                                if group['cats'] != first_group_cats:
                                    all_match = False
                                    break
                        if all_match:
                            is_shared = True
                            shared_cats_str = " / ".join(first_group_cats)

                    if is_shared:
                        names = " / ".join([g['name'] for g in grouped_labels])
                        label_str = f"Label: {names} {shared_cats_str}".strip()
                    else:
                        has_multi_cats = any(len(g['cats']) > 1 for g in grouped_labels)
                        sep = " - " if has_multi_cats else " / "

                        parts = []
                        for group in grouped_labels:
                            if group['cats']:
                                cat_str = " / ".join(group['cats'])
                                parts.append(f"{group['name']} {cat_str}".strip())
                            else:
                                parts.append(group['name'])
                        label_str = f"Label: {sep.join(parts)}"
            
            # --- 4. Advanced Format Logic (Tiered Metadata & Blocks) ---
            raw_formats = data.get('formats', [])
            

            def get_fmt_text_blob(fmt_list):
                blob = ""
                for f in fmt_list:
                    blob += f.get('name', '') + " "
                    blob += " ".join(f.get('descriptions', [])) + " "
                    blob += (f.get('text', '') or "") + " "
                return blob


            all_blob = get_fmt_text_blob(raw_formats)

            # 1. The "Edition Splitter" (Global Tags)
            slash_group_tags = []
            space_group_tags = []
            
            settings_data = load_json_data("data.json")
            
            # Load Format Tags order for sorting
            format_tags_order = []
            if settings_data and "Format Tags" in settings_data:
                format_tags_order = settings_data["Format Tags"]

            def sort_tags_by_settings(tags_list):
                if not format_tags_order: return tags_list
                def sort_key(t):
                    if t in format_tags_order: return format_tags_order.index(t)
                    for i, ft in enumerate(format_tags_order):
                        if ft.lower() == t.lower(): return i
                    return 9999
                return sorted(tags_list, key=sort_key)

            # Default whitelist

            slash_whitelist = ["Deluxe Edition", "Limited Edition", "Special Edition", "Club Edition"]

            if settings_data is not None:
                if "Slash Separated Editions" in settings_data:
                    slash_whitelist = settings_data["Slash Separated Editions"]

                for tag in settings_data.get("Edition", []):
                    if tag in slash_whitelist:
                        slash_group_tags.append(tag)
                    else:
                        space_group_tags.append(tag)
            else:
                # Fallback if file read fails
                slash_group_tags = slash_whitelist
                space_group_tags = ["Numbered", "Record Store Day", "Compilation", "Anniversary", "Alternate Cover", "Clean Version", "RSD", "Autographed"]
            
            found_slash_tags = []
            for tag in slash_group_tags:
                if tag in all_blob and tag not in found_slash_tags:
                    found_slash_tags.append(tag)
            
            found_space_tags = []
            for tag in space_group_tags:
                if tag in all_blob and tag not in found_space_tags:
                    found_space_tags.append(tag)


            # Construct the display string
            edition_display_parts = []
            
            # Handle Slash Group
            if found_slash_tags:
                # "Deluxe / Limited / Special / Club Edition"
                prefixes = [t.replace(" Edition", "") for t in found_slash_tags]
                edition_display_parts.append(" / ".join(prefixes) + " Edition")
            
            # Handle Space Group
            if found_space_tags:
                edition_display_parts.append(" ".join(found_space_tags))
                # Don't include Out-of-Print here, let it be handled as a normal tag.
                # This is a workaround for a potential client-side issue where edition tags
                # are not included in the generated description.
                space_group_for_display = [t for t in found_space_tags if t != "Out-of-Print"]
                if space_group_for_display:
                    edition_display_parts.append(" ".join(space_group_for_display))
            
            # Combine into one string for the Format line
            global_editions_str = " ".join(edition_display_parts)
            
            # List for exclusions (original tags)
            detected_global_editions = found_slash_tags + found_space_tags
            
            # Extract any other stray format tags (like Misprint) from global format elements
            # (e.g. "All Media" or "Box Set") that are otherwise skipped by the format block processors
            # We want to capture Edition tags, Format Tags, and Packaging features from global blocks
            global_tag_whitelist = ["Remastered", "Reissue", "Repress", "Mispress", "Misprint", "Promo", "NTSC", "Enhanced", "PAL", "SECAM", "Multichannel", "Quadraphonic", "Mono", "Remixed", "Digipak", "Gatefold", "Numbered"]
            if settings_data:
                for cat in ["Format Tags", "Sleeve Packaging", "Packaging Feature", "Edition"]:
                    if cat in settings_data:
                        global_tag_whitelist.extend(settings_data[cat])
            
            global_formats = [f for f in raw_formats if f.get('name') in ['All Media', 'Box Set']]
            for f in global_formats:
                g_tags = list(f.get('descriptions', []))
                if f.get('text'):
                    g_tags.extend([t.strip() for t in re.split(r'[/,;]', f.get('text'))])
                for tag in g_tags:
                    tag = tag.strip()
                    # If tag is in our expanded whitelist, and not already in our global editions
                    if tag and tag in global_tag_whitelist and tag not in detected_global_editions:
                        detected_global_editions.append(tag)
                        if global_editions_str:
                            global_editions_str += " " + tag
                        else:
                            global_editions_str = tag
            
            # Exclude Out-of-Print from the edition tags so it can be picked up by format blocks.
            detected_global_editions = [t for t in detected_global_editions if t != "Out-of-Print"]


            # 2. Format Blocks
            blocks = []

            # [CD Multiplier]
            # Capture CD, CDr, SACD, etc.
            cd_formats = [f for f in raw_formats if f.get('name') in ['CD', 'CDr', 'SACD', 'Hybrid']]

            if cd_formats:
                cd_blob = get_fmt_text_blob(cd_formats)
                total_qty = 0
                for f in cd_formats: 
                    try:
                        total_qty += int(f.get('qty', 1))
                    except (ValueError, TypeError):
                        total_qty += 1
                

                # Fallback: If qty is 1 but text says "2 x" or "3 x", trust the text
                if total_qty <= 1:
                    if "2 x" in cd_blob or "2x" in cd_blob: total_qty = 2
                    elif "3 x" in cd_blob or "3x" in cd_blob: total_qty = 3
                    elif "4 x" in cd_blob or "4x" in cd_blob: total_qty = 4
                

                qty_str = f"{total_qty}x" if total_qty > 1 else ""
                
                cd_tags = []
                # Added CDr, SACD to exclusions so they don't duplicate in the tag list
                exclusions = detected_global_editions + ["CD", "CDr", "SACD", "Hybrid", "Album", "Box Set"]
                exclusions = detected_global_editions + ["CD", "CDr", "SACD", "Hybrid", "Album", "Box Set", "Stereo"]
                for f in cd_formats:
                    raw_tags = list(f.get('descriptions', []))
                    if f.get('text'):
                        raw_tags.extend([t.strip() for t in re.split(r'[/,;]', f.get('text'))])
                    
                    for tag in raw_tags:
                        tag = tag.strip()
                        if tag and tag not in exclusions and tag not in cd_tags:
                            cd_tags.append(tag)

                
                # Determine base name (CD vs CDr etc) - Default to CD if mixed
                base_name = "CD"
                if all(f.get('name') == 'CDr' for f in cd_formats): base_name = "CDr"
                elif all(f.get('name') == 'SACD' for f in cd_formats): base_name = "SACD"
                
                if any(t.lower() in ['maxi-single', 'maxi single'] for t in cd_tags):

                    cd_tags = [t for t in cd_tags if t.lower() != 'single']

                cd_tags = sort_tags_by_settings(cd_tags)
                blocks.append(f"{' '.join(cd_tags)} {qty_str}{base_name}".strip().replace("  ", " "))


            # [LP & Weight Logic]
            vinyl_formats = [f for f in raw_formats if f.get('name') in ['Vinyl', 'LP']]
            # Discogs sometimes puts "LP" in text, not descriptions, so check both
            lp_formats = [f for f in vinyl_formats if "LP" in f.get('descriptions', []) or "LP" in f.get('text', '')]
            
            if lp_formats:
                lp_blob = get_fmt_text_blob(lp_formats)
                # Calculate total quantity from API 'qty' field
                total_qty = 0
                for f in lp_formats:
                    try:
                        total_qty += int(f.get('qty', 1))
                    except (ValueError, TypeError):
                        total_qty += 1
                
                # Fallback: If qty is 1 but text says "2 x" or "3 x", trust the text
                if total_qty <= 1:
                    if "2 x" in lp_blob or "2x" in lp_blob: total_qty = 2
                    elif "3 x" in lp_blob or "3x" in lp_blob: total_qty = 3
                    elif "4 x" in lp_blob or "4x" in lp_blob: total_qty = 4

                lp_qty = f"{total_qty}x" if total_qty > 1 else ""

                lp_tags = []
                if "Reissue" in lp_blob: lp_tags.append("Reissue")
                if "Remastered" in lp_blob: lp_tags.append("Remastered")
                if re.search(r'\b180\s*g(ram)?s?\b', lp_blob, re.IGNORECASE): lp_tags.append("180g")
                if re.search(r'\b200\s*g(ram)?s?\b', lp_blob, re.IGNORECASE): lp_tags.append("200g")
                if re.search(r'\b140\s*g(ram)?s?\b', lp_blob, re.IGNORECASE): lp_tags.append("140g")
                if "Picture Disc" in lp_blob: lp_tags.append("Picture Disc")
                
                # Add RPMs to tags so they can be multi-selected with weight
                if "45 RPM" in lp_blob: lp_tags.append("45 RPM")
                if "33 ⅓ RPM" in lp_blob: lp_tags.append("33 ⅓ RPM")
                if "78 RPM" in lp_blob: lp_tags.append("78 RPM")
                
                # Color Detection
                known_colors = ["Gold", "Silver", "Clear", "Red", "Blue", "White", "Green", "Yellow", "Pink", "Orange", "Purple", "Splatter", "Swirl", "Marble", "Teal", "Turquoise", "Black", "Brown", "Grey", "Gray", "Coke Bottle", "Translucent", "Transparent", "Crystal", "Rainbow", "Glow In The Dark", "Glow-in-the-Dark", "Glow", "Beige", "Cream", "Tan", "Violet", "Burgundy", "Magenta", "Peach", "Lime", "Rose", "Amber", "Neon"]
                
                # Try to load custom colors from data.json
                settings = load_json_data("data.json")
                if settings and "Color" in settings and isinstance(settings["Color"], list):
                    known_colors = settings["Color"]

                for color in known_colors:
                    # Check for color as a whole word (case-insensitive)
                    if re.search(r'\b' + re.escape(color) + r'\b', lp_blob, re.IGNORECASE):
                        lp_tags.append(color)
                
                # Catch-all for other tags (descriptions & free text)
                exclusions = detected_global_editions + ["Vinyl", "LP", "Album", "Box Set", "12\"", "33 ⅓ RPM", "45 RPM", "Stereo", "Mono"]
                exclusions = detected_global_editions + ["Vinyl", "LP", "Album", "Box Set", "12\"", "33 ⅓ RPM", "45 RPM", "Stereo"]
                for f in lp_formats:
                    raw_tags = list(f.get('descriptions', []))
                    if f.get('text'):
                        raw_tags.extend([t.strip() for t in re.split(r'[/,;]', f.get('text'))])
                    
                    for tag in raw_tags:
                        tag = tag.strip()
                        if not tag or tag in exclusions: continue
                        if re.match(r'^180\s*g(ram)?s?$', tag, re.IGNORECASE) and "180g" in lp_tags: continue
                        if re.match(r'^200\s*g(ram)?s?$', tag, re.IGNORECASE) and "200g" in lp_tags: continue
                        if re.match(r'^140\s*g(ram)?s?$', tag, re.IGNORECASE) and "140g" in lp_tags: continue
                        if tag == "Picture Disc" and "Picture Disc" in lp_tags: continue
                        if tag not in lp_tags:
                            lp_tags.append(tag)

                # Deduplicate tags while preserving order (Case Insensitive)
                seen_lower = set()
                deduped_lp = []
                for t in lp_tags:
                    if t.lower() not in seen_lower:
                        seen_lower.add(t.lower())
                        deduped_lp.append(t)
                lp_tags = deduped_lp

                lp_tags = sort_tags_by_settings(lp_tags)
                if any(t.lower() in ['maxi-single', 'maxi single'] for t in lp_tags):
                    lp_tags = [t for t in lp_tags if t.lower() != 'single']

                blocks.append(f"{' '.join(lp_tags)} {lp_qty}LP Vinyl".strip())

            # [Singles & Speed Rule]

            # Filter out formats already processed as LPs to prevent duplication (e.g. "Album" + "12"")
            non_lp_formats = [f for f in vinyl_formats if f not in lp_formats]
            
            if non_lp_formats:
                vinyl_blob = get_fmt_text_blob(non_lp_formats)
                has_7 = '7"' in vinyl_blob
                has_10 = '10"' in vinyl_blob
                has_12 = '12"' in vinyl_blob
                has_album = "Album" in vinyl_blob
                
                if has_7 or has_10 or has_12 or has_album:
                    # Calculate Qty for non-LP vinyl (e.g. 2x12")
                    total_qty = 0
                    for f in non_lp_formats:
                        try:
                            total_qty += int(f.get('qty', 1))
                        except (ValueError, TypeError):
                            total_qty += 1
                    
                    # Fallback check in text blob
                    if total_qty <= 1:
                        if "2 x" in vinyl_blob or "2x" in vinyl_blob: total_qty = 2
                        elif "3 x" in vinyl_blob or "3x" in vinyl_blob: total_qty = 3
                    
                    qty_str = f"{total_qty}x" if total_qty > 1 else ""

                    speed = "45 RPM" if "45 RPM" in vinyl_blob else ""
                    sizes = [s for s in ['7"', '10"', '12"'] if s in vinyl_blob]
                    if not sizes and has_album: sizes = ['12"']
                    
                    # Extract tags (Reissue, etc) for non-LP vinyl
                    other_tags = []
                    post_fm_tags = []

                    if "Reissue" in vinyl_blob: other_tags.append("Reissue")
                    if "Remastered" in vinyl_blob: other_tags.append("Remastered")
                    if "Picture Disc" in vinyl_blob: post_fm_tags.append("Picture Disc")
                    if "Promo" in vinyl_blob: other_tags.append("Promo")
                    if "Maxi-Single" in vinyl_blob: post_fm_tags.append("Maxi-Single")
                    elif "Single" in vinyl_blob: post_fm_tags.append("Single")
                    if "Mini-Album" in vinyl_blob: other_tags.append("Mini-Album")
                    if re.search(r'\b180\s*g(ram)?s?\b', vinyl_blob, re.IGNORECASE): other_tags.append("180g")
                    if re.search(r'\b200\s*g(ram)?s?\b', vinyl_blob, re.IGNORECASE): other_tags.append("200g")
                    if re.search(r'\b140\s*g(ram)?s?\b', vinyl_blob, re.IGNORECASE): other_tags.append("140g")
                    
                    # Color Detection for Singles
                    known_colors = ["Gold", "Silver", "Clear", "Red", "Blue", "White", "Green", "Yellow", "Pink", "Orange", "Purple", "Splatter", "Swirl", "Marble", "Teal", "Turquoise", "Black", "Brown", "Grey", "Gray", "Coke Bottle", "Translucent", "Transparent", "Crystal", "Rainbow", "Glow In The Dark", "Glow-in-the-Dark", "Glow", "Beige", "Cream", "Tan", "Violet", "Burgundy", "Magenta", "Peach", "Lime", "Rose", "Amber", "Neon"]
                    
                    settings = load_json_data("data.json")
                    if settings and "Color" in settings and isinstance(settings["Color"], list):
                        known_colors = settings["Color"]

                    for color in known_colors:
                        if re.search(r'\b' + re.escape(color) + r'\b', vinyl_blob, re.IGNORECASE):
                            other_tags.append(color)
                    

                    ep_str = " EP" if re.search(r'\bEP\b', vinyl_blob, re.IGNORECASE) else ""

                    if sizes:
                        other_tags = sort_tags_by_settings(other_tags)
                        size_str = ' & '.join(sizes)
                        post_fm_str = " " + " ".join(post_fm_tags) if post_fm_tags else ""
                        blocks.append(f"{' '.join(other_tags)} {speed} {qty_str}{size_str}{ep_str} Vinyl{post_fm_str}".strip())

            # [Cassette Block]

            cassette_formats = [f for f in raw_formats if f.get('name') == 'Cassette']
            if cassette_formats:
                total_qty = 0
                for f in cassette_formats:
                    try:
                        total_qty += int(f.get('qty', 1))
                    except (ValueError, TypeError):
                        total_qty += 1
                qty_str = f"{total_qty}x" if total_qty > 1 else ""
                
                cass_tags = []
                exclusions = detected_global_editions + ["Cassette", "Album", "Box Set"]
                exclusions = detected_global_editions + ["Cassette", "Album", "Box Set", "Stereo"]
                for f in cassette_formats:
                    raw_tags = list(f.get('descriptions', []))
                    if f.get('text'):
                        raw_tags.extend([t.strip() for t in re.split(r'[/,;]', f.get('text'))])
                    
                    for tag in raw_tags:
                        tag = tag.strip()
                        if tag and tag not in exclusions and tag not in cass_tags:
                            cass_tags.append(tag)

                if any(t.lower() in ['maxi-single', 'maxi single'] for t in cass_tags):
                    cass_tags = [t for t in cass_tags if t.lower() != 'single']

                cass_tags = sort_tags_by_settings(cass_tags)
                blocks.append(f"{' '.join(cass_tags)} {qty_str}Cassette".strip().replace("  ", " "))

            # [Video & Other Media Block]

            target_others = ["DVD", "Blu-ray", "Blu-ray Audio", "DVD-Audio", "VHS", "Laserdisc", "Betamax", "HD DVD", "Minidisc"]
            other_formats = [f for f in raw_formats if f.get('name') in target_others]
            
            other_groups = {}
            for f in other_formats:
                fname = f.get('name')
                if fname not in other_groups: 
                    other_groups[fname] = {'qty': 0, 'tags': []}
                
                try:
                    other_groups[fname]['qty'] += int(f.get('qty', 1))
                except:
                    other_groups[fname]['qty'] += 1
                
                # Collect descriptions and text
                raw_tags = list(f.get('descriptions', []))
                if f.get('text'):
                    raw_tags.extend([t.strip() for t in re.split(r'[/,;]', f.get('text'))])
                
                for tag in raw_tags:
                    tag = tag.strip()
                    if tag and tag not in other_groups[fname]['tags']:
                        other_groups[fname]['tags'].append(tag)
            
            for fname, group_data in other_groups.items():
                q = group_data['qty']
                q_str = f"{q}x" if q > 1 else ""
                
                # Filter tags
                tags = [t for t in group_data['tags'] if t not in detected_global_editions and t != fname and t not in ["Stereo", "Album", "Box Set"]]
                
                if any(t.lower() in ['maxi-single', 'maxi single'] for t in tags):
                    tags = [t for t in tags if t.lower() != 'single']
                if any(t.lower() in ['mini-album', 'mini album'] for t in tags):
                    tags = [t for t in tags if t.lower() != 'album']

                # Check for specific format overrides in tags (e.g. DVD-Video replacing DVD)
                # If a tag starts with the format name (e.g. "DVD-Video" starts with "DVD"), use the tag as the format
                override_fmt = None
                for t in tags:
                    if t.lower().startswith(fname.lower()) and len(t) > len(fname):
                        override_fmt = t
                        break
                
                if override_fmt:
                    fname = override_fmt
                    tags.remove(override_fmt)
                
                tags = sort_tags_by_settings(tags)

                tag_str = " ".join(tags)
                
                blocks.append(f"{tag_str} {q_str}{fname}".strip().replace("  ", " "))

            # [Box Set Assembly]

            if "Box Set" in all_blob and blocks:
                blocks[-1] = blocks[-1] + " Box Set"
            
            # Final String Construction
            # Format: [Global Editions], [Format Blocks joined by +]
            fmt_parts = ([global_editions_str] if global_editions_str else []) + [" + ".join([b for b in blocks if b])]
            formats_str = ", ".join([p for p in fmt_parts if p])

            
            if not formats_str: formats_str = "Unknown Format"

            tracks = data.get('tracklist', [])
            track_count = len([t for t in tracks if t.get('type_') != 'heading'])
            tracklist_str = "\n".join([f"{t.get('position','')} {t.get('title','')} {t.get('duration','')}".strip() for t in tracks])

            country = data.get('country') or ""
            country = str(country).strip()
            if country.lower() in ["n/a", "none"]:
                country = ""
            
            released = data.get('released') or ""
            if released == "N/A": released = ""

            raw_text_tool = f"{artist} - {album}\n{label_str}\nFormat: {formats_str}\nCountry: {country}\nReleased: {released}\nTrack Count: {track_count}\n\nTracklist\n{tracklist_str}"

            if is_master:
                raw_text_tool = "--- Scraped via Master Release ---\n" + raw_text_tool

            save_to_history({"title": f"{artist} - {album}", "url": url, "raw_text": raw_text_tool})

            # Prepare data for JS injection (JSON encoded to handle special chars/newlines safely)
            json_raw_text = json.dumps(raw_text_tool).replace("</", "<\\/")
            json_tracklist = json.dumps(tracklist_str).replace("</", "<\\/")

            response_content = f"""
            <script>
                (function() {{
                    // Inject data dynamically to avoid layout shifts in the response container
                    let container = document.getElementById('scrapedDataContainer');
                    if (container) container.remove();
                    
                    container = document.createElement('div');
                    container.id = 'scrapedDataContainer';
                    container.style.display = 'none';
                    
                    const pre = document.createElement('pre');
                    pre.id = 'scraperResultText';
                    pre.textContent = {json_raw_text};
                    
                    const textarea = document.createElement('textarea');
                    textarea.id = 'hiddenTracklist';
                    textarea.value = {json_tracklist};
                    
                    container.appendChild(pre);
                    container.appendChild(textarea);
                    document.body.appendChild(container);

                    // Try to find the button by ID, then by text content
                    let scrapeBtn = document.getElementById('scrapeBtn') || document.getElementById('scrape-button');
                    if (!scrapeBtn) {{
                        const buttons = document.getElementsByTagName('button');
                        for (let btn of buttons) {{
                            if (btn.innerText.trim() === 'Scrape') {{
                                scrapeBtn = btn;
                                break;
                            }}
                        }}
                    }}

                    if (scrapeBtn) {{
                        const originalText = scrapeBtn.innerText || scrapeBtn.value;
                        const isInput = scrapeBtn.tagName === 'INPUT';
                        
                        if (isInput) scrapeBtn.value = '✅ Scraped!';
                        else scrapeBtn.innerHTML = '✅ Scraped!';
                        
                        scrapeBtn.disabled = true;
                        
                        setTimeout(() => {{
                            if (isInput) scrapeBtn.value = originalText;
                            else scrapeBtn.innerHTML = originalText;
                            scrapeBtn.disabled = false;
                        }}, 2000);
                    }}
                    
                    const rawText = document.getElementById('scraperResultText')?.textContent || '';
                    if (rawText) {{
                        // Populate builder tab
                        if (typeof parsePastedData === 'function') {{
                            parsePastedData(rawText);
                        }}
                        // Populate details tab scratchpad
                        const manualInput = document.getElementById('manualInputBox');
                        if (manualInput) {{
                            manualInput.value = rawText;
                        }}
                    }}

                    // Also refresh the history list automatically
                    if (window.htmx) htmx.trigger('#historyList', 'load');

                    // Automatically generate listing data if Auto Generate is checked
                    const autoGen = document.getElementById('autoGenerateToggle');
                    if (autoGen && autoGen.checked && typeof generateListingData === 'function') {{
                        setTimeout(() => {{
                            generateListingData();
                        }}, 50);
                    }}
                }})();
            </script>
            """
            return HTMLResponse(content=response_content)
        except Exception as e:
            return HTMLResponse(f"Scraper Error: {str(e)}")

@app.post("/shutdown")
async def shutdown():
    # Terminate tracked child processes
    for name, proc in CHILD_PROCESSES.items():
        if proc and proc.poll() is None:
            try:
                logging.info(f"Terminating child process: {name}")
                proc.terminate()
            except Exception as e:
                logging.error(f"Error terminating {name}: {e}")

    threading.Thread(target=lambda: (time.sleep(1), os.kill(os.getpid(), signal.SIGTERM))).start()
    return HTMLResponse("<h3>Shutdown Successful.</h3>")
@app.post("/market-search")


async def market_search(data: dict = Body(...)):
    artist = data.get("artist", "").strip()
    title = data.get("title", "").strip()
    upc = data.get("upc", "").strip()

    # Determine the best search string
    search_query = upc if upc else (f"{artist} {title}" if artist and title else (artist or title))

    if not search_query:
        # Return HTML instead of JSON to prevent the "Unexpected Token" error
        return HTMLResponse("<p style='color:red;'>Please enter a UPC or Artist name.</p>")

    # Generate links
    amazon_link = f"https://www.amazon.com/s?k={search_query.replace(' ', '+')}"
    discogs_link = f"https://www.discogs.com/search/?q={search_query.replace(' ', '+')}&type=all"

    # The exact HTML to inject into the "lookupResults" div
    html_content = f"""
        <div style="background: var(--bg-content, white); color: var(--text-main, #333); border: 1px solid var(--border-color, #ddd); padding: 15px; border-radius: 8px;">
            <h4 style="margin-top:0; color: var(--text-main, #333);">Market Links for: "{search_query}"</h4>
            <div style="display: flex; gap: 10px;">
                <a href="{amazon_link}" target="_blank" style="flex:1; text-align:center; background:#FF9900; color:black; padding:10px; text-decoration:none; border-radius:4px; font-weight:bold;">Check Amazon</a>
                <a href="{discogs_link}" target="_blank" style="flex:1; text-align:center; background:#333; color:white; padding:10px; text-decoration:none; border-radius:4px; font-weight:bold;">Check Discogs</a>
            </div>
        </div>
    """
    
    return HTMLResponse(content=html_content)
    
def get_today_counts_data():
    # Determine filename based on today's date
    filename = datetime.now().strftime("%Y-%m-%d") + "_Listings.txt"
    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = today_str + "_Listings.txt"
    
    # Save to a "Listings" subfolder to keep root clean
    listings_dir = get_local_path("Listings")
    if not os.path.exists(listings_dir):
        os.makedirs(listings_dir)
    
    # Cleanup old files (reset logic: delete yesterday's/old files)
    try:
        for f in os.listdir(listings_dir):
            if f.endswith("_Listings.txt") and f != filename:
                try:
                    os.remove(os.path.join(listings_dir, f))
                except Exception as e:
                    logging.error(f"Failed to delete old listing file {f}: {e}")
    except Exception as e:
        logging.error(f"Error cleaning up listings folder: {e}")

    file_path = os.path.join(listings_dir, filename)
    
    counts = {"Listed": 0, "Amazon Adds": 0, "Discogs Adds": 0, "Duplicates": 0}
    
    # Read existing counts if file exists
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        try:
                            val = int(parts[1].strip())
                            counts[key] = val
                        except: pass
        except: pass
    return counts, file_path

@app.get("/api/get-counters")
async def get_counters_endpoint():
    counts, _ = get_today_counts_data()
    return counts

@app.post("/api/increment-counter")
async def increment_counter(data: dict = Body(...)):
    counter_type = data.get("type")
    label = data.get("label")
    counts, file_path = get_today_counts_data()

    if label:
        counts[label] = counts.get(label, 0) + 1
    else:
        # Fallback for old/default types
        if counter_type == "L":
            counts["Listed"] = counts.get("Listed", 0) + 1
        elif counter_type == "AA":
            counts["Amazon Adds"] = counts.get("Amazon Adds", 0) + 1
        elif counter_type == "DA":
            counts["Discogs Adds"] = counts.get("Discogs Adds", 0) + 1
        elif counter_type == "D":
            counts["Duplicates"] = counts.get("Duplicates", 0) + 1
        
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for k, v in counts.items():
                f.write(f"{k}: {v}\n")
        return {"status": "success", "counts": counts}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

def is_port_in_use(port):
    """Checks if a local port is listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)  # Prevent hanging if port is unresponsive
        # Returns 0 if connection successful (port in use)
        return s.connect_ex(('127.0.0.1', port)) == 0

@app.get("/api/service-status")
async def get_service_status():
    """Checks if external tools are currently running."""
    uberpaste = False
    wysiscan = False
    wysichat = False
    
    # Check WysiScan by port 8010 (Standardized)
    target_port = 8010
    wysiscan = is_port_in_use(target_port)

    try:
        for p in psutil.process_iter(['name', 'cmdline']):
            try:
                if not p.info['cmdline']: continue
                # Join cmdline to string for easier searching
                cmd = ' '.join(p.info['cmdline'])
                
                # Check for UberPaste (Script or Frozen)
                if "UberPaste.py" in cmd or "--uberpaste" in cmd:
                    uberpaste = True
                
                # Check for WysiChat (Script or Frozen)
                if 'WysiChat.exe' in p.info['name'] or 'WysiChat' in cmd or '--wysichat' in cmd:
                    wysichat = True

                if uberpaste and wysichat: # Early exit if all found
                    break 
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception:
        pass
            
    return {"wysiscan": wysiscan, "uberpaste": uberpaste, "wysichat": wysichat}

# --- LOGGING CONFIGURATION ---
logging.basicConfig(
    handlers=[RotatingFileHandler('wysiwyg_debug.log', maxBytes=5*1024*1024, backupCount=5)],
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    import uvicorn # Already imported
    import webbrowser # Already imported
    import os # Already imported
    import sys # Already imported
    
    logging.info(f"Executable entry point called with sys.argv: {sys.argv}")

    # --- DISPATCHER FOR SUB-PROCESSES (FROZEN MODE) ---
    if getattr(sys, 'frozen', False):
        if "-c" in sys.argv:
            try:
                sys.path.append(sys._MEIPASS)
                c_index = sys.argv.index("-c")
                code_to_run = sys.argv[c_index + 1]
                exec(code_to_run)
                sys.exit()
            except Exception as e:
                import traceback
                logging.error(f"Failed to execute dynamic code via -c: {e}\n{traceback.format_exc()}")
                with open("wysiwyg_debug.log", "a", encoding="utf-8") as f_log:
                    f_log.write(f"\nCRITICAL - Dynamically executed code crash via -c: {e}\n{traceback.format_exc()}\n")
                sys.exit(1)

        if "--uberpaste" in sys.argv:
            # Add sys._MEIPASS to path so we can import the bundled modules
            sys.path.append(sys._MEIPASS)
            # Import and run UberPaste
            from Uberpaste.UberPaste import main as run_uberpaste
            run_uberpaste()
            sys.exit()
            
        if "--wysiscan" in sys.argv:
            try:
                sys.path.append(sys._MEIPASS)
                # Import and run WysiScan
                from WysiScan.scanner_server import run_server as run_wysiscan
                run_wysiscan()
                sys.exit()
            except Exception as e:
                import traceback
                logging.error(f"WysiScan failed under --wysiscan: {e}\n{traceback.format_exc()}")
                with open("wysiwyg_debug.log", "a", encoding="utf-8") as f_log:
                    f_log.write(f"\nCRITICAL - WysiScan subprocess crash: {e}\n{traceback.format_exc()}\n")
                sys.exit(1)

        if "--imageconvert" in sys.argv:
            try:
                sys.path.append(sys._MEIPASS)
                sys.argv.remove("--imageconvert")
                from WysiScan.imageconvert.app import main as run_imageconvert
                run_imageconvert()
                sys.exit()
            except Exception as e:
                import traceback
                logging.error(f"Image Converter failed under --imageconvert: {e}\n{traceback.format_exc()}")
                with open("wysiwyg_debug.log", "a", encoding="utf-8") as f_log:
                    f_log.write(f"\nCRITICAL - Image Converter subprocess crash: {e}\n{traceback.format_exc()}\n")
                sys.exit(1)

    # Prevent multiple instances of the main application
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        
        global _instance_mutex
        # Use Local namespace (no "Global\" prefix) to avoid ERROR_ACCESS_DENIED when run as non-admin
        _instance_mutex = kernel32.CreateMutexW(None, False, "Local\\WYSIWYG_SINGLE_INSTANCE_MUTEX")
        last_error = ctypes.get_last_error()
        if last_error in (5, 183):  # ERROR_ACCESS_DENIED (5) or ERROR_ALREADY_EXISTS (183)
            logging.info(f"Another instance is already running (error {last_error}). Exiting.")
            sys.exit(0)

    logging.info("--- APPLICATION STARTING ---")

    # --- ROBUST PROCESS CLEANUP ---
    # Only clean up other instances if running as the frozen application (Production)
    if getattr(sys, 'frozen', False):
        try:
            current_pid = os.getpid()
            logging.info(f"Current Process ID: {current_pid}")
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    # Check for other instances of lister.exe
                    if proc.info['name'] == "WYSIWYG.exe" and proc.info['pid'] != current_pid:
                        logging.info(f"Found old instance (PID {proc.info['pid']}). Terminating...")
                        proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            logging.error(f"Cleanup Error: {e}")

    init_cost_calc()
    
    # --- UBERPASTE STARTUP ---
    def auto_start_uberpaste():
        logging.info("Auto-starting UberPaste...")
        for p in psutil.process_iter(['cmdline']):
            try:
                if p.info['cmdline']:
                    cmd_str = ' '.join(p.info['cmdline'])
                    if 'UberPaste.py' in cmd_str or '--uberpaste' in cmd_str:
                        return
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, "--uberpaste"])
            else:
                up_path = resource_path(os.path.join("Uberpaste", "UberPaste.py"))
                if os.path.exists(up_path):
                    subprocess.Popen([sys.executable, up_path])
        except Exception as e:
            logging.error(f"Auto-start UberPaste failed: {e}")

    threading.Timer(1.5, auto_start_uberpaste).start()

    init_conditions()

    # --- LAUNCH MODE: browser by default, PySide6 window via --window ---
    # Must be defined BEFORE starting the server thread (it reads BIND_HOST).
    USE_WINDOW = "--window" in sys.argv
    BIND_HOST = "0.0.0.0" if "--host" in sys.argv else "127.0.0.1"

    # --- SERVER STARTUP ---
    def start_uvicorn():
        try:
            logging.info("Starting Uvicorn server...")
            uvicorn.run(app, host=BIND_HOST, port=8008, log_config=None, access_log=False)
        except Exception as e:
            logging.critical(f"SERVER CRASHED: {e}", exc_info=True)

    server_thread = threading.Thread(target=start_uvicorn, daemon=True)
    server_thread.start()

    # Wait until local FastAPI server is listening on port 8008
    for _ in range(50):
        if is_port_in_use(8008):
            break
        time.sleep(0.1)

    # --- PYSIDE6 GUI STARTUP (opt-in) ---
    if USE_WINDOW:
        from PySide6.QtCore import QUrl, QTimer, QSettings, Qt
        from PySide6.QtGui import QIcon, QFontDatabase
        from PySide6.QtWidgets import (QApplication, QMainWindow, QDialog, QFormLayout,
                                     QSlider, QSpinBox, QComboBox, QPushButton,
                                     QHBoxLayout, QVBoxLayout, QLabel)
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile

        class GuiAdjustDialog(QDialog):
            def __init__(self, parent, view):
                super().__init__(parent)
                self.setWindowTitle("GUI Adjust Settings")
                self.resize(380, 200)
                self.view = view
                self.qsettings = QSettings("FYR", "WYSIWYG")
            
                layout = QVBoxLayout(self)
                form = QFormLayout()
            
                # Zoom factor (50% - 200%)
                self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
                self.zoom_slider.setRange(50, 200)
                current_zoom = int(self.qsettings.value("zoom_factor", 100))
                self.zoom_slider.setValue(current_zoom)
                self.zoom_label = QLabel(f"{current_zoom}%")
                self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
                zoom_row = QHBoxLayout()
                zoom_row.addWidget(self.zoom_slider)
                zoom_row.addWidget(self.zoom_label)
                form.addRow("GUI Zoom:", zoom_row)
            
                # Font size (10px - 30px)
                self.font_size_spin = QSpinBox()
                self.font_size_spin.setRange(10, 30)
                current_size = int(self.qsettings.value("font_size", 12))
                self.font_size_spin.setValue(current_size)
                self.font_size_spin.valueChanged.connect(self.on_font_size_changed)
                form.addRow("Font Size (px):", self.font_size_spin)
            
                # Font Family
                self.font_combo = QComboBox()
                common_fonts = ["Arial", "Segoe UI", "Inter", "Roboto", "Helvetica", "Times New Roman", "Courier New", "Verdana"]
                system_fonts = QFontDatabase.families()
                all_fonts = []
                for f in common_fonts:
                    if f in system_fonts:
                        all_fonts.append(f)
                for f in system_fonts:
                    if f not in all_fonts:
                        all_fonts.append(f)
                self.font_combo.addItems(all_fonts)
                current_font = self.qsettings.value("font_family", "Arial")
                idx = self.font_combo.findText(current_font)
                if idx >= 0:
                    self.font_combo.setCurrentIndex(idx)
                self.font_combo.currentTextChanged.connect(self.on_font_family_changed)
                form.addRow("Font Family:", self.font_combo)
            
                layout.addLayout(form)
            
                btn_box = QHBoxLayout()
                close_btn = QPushButton("Close")
                close_btn.clicked.connect(self.accept)
                btn_box.addStretch()
                btn_box.addWidget(close_btn)
                layout.addLayout(btn_box)
            
            def on_zoom_changed(self, val):
                self.zoom_label.setText(f"{val}%")
                self.view.setZoomFactor(val / 100.0)
                self.qsettings.setValue("zoom_factor", val)
            
            def on_font_size_changed(self, val):
                s = self.view.settings()
                s.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, val)
                self.qsettings.setValue("font_size", val)
            
            def on_font_family_changed(self, family):
                s = self.view.settings()
                s.setFontFamily(QWebEngineSettings.FontFamily.StandardFont, family)
                self.qsettings.setValue("font_family", family)

        class CustomWebPage(QWebEnginePage):
            def __init__(self, profile, parent=None):
                super().__init__(profile, parent)
                self.windows = []
                self.permissionRequested.connect(self.handle_permission)

            def handle_permission(self, permission):
                permission.grant()

            def createWindow(self, type_):
                new_window = QMainWindow()
                new_window.resize(1200, 900)
            
                icon_path = resource_path("fyr-logo.ico")
                if os.path.exists(icon_path):
                    new_window.setWindowIcon(QIcon(icon_path))
                
                new_view = QWebEngineView(new_window)
                new_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
                new_page = CustomWebPage(self.profile(), new_view)
                new_view.setPage(new_page)
                new_window.setCentralWidget(new_view)
                new_page.windowCloseRequested.connect(new_window.close)
            
                self.windows.append(new_window)
            
                original_close = new_window.closeEvent
                def close_event(event):
                    if new_window in self.windows:
                        self.windows.remove(new_window)
                    if original_close:
                        original_close(event)
                new_window.closeEvent = close_event

                new_window.show()
                return new_page

        qt_app = QApplication(sys.argv)
        profile = QWebEngineProfile("wysiwyg_profile")
    
        main_window = QMainWindow()
        version_str = get_current_version_str()
        main_window.setWindowTitle(f"WYSIWYG - v{version_str}")
        main_window.resize(1400, 950)
    
        icon_path = resource_path("fyr-logo.ico")
        if os.path.exists(icon_path):
            main_window.setWindowIcon(QIcon(icon_path))
        
        main_view = QWebEngineView(main_window)
        main_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        main_page = CustomWebPage(profile, main_view)
        main_view.setPage(main_page)
        main_view.setUrl(QUrl("http://127.0.0.1:8008"))
    
        main_window.setCentralWidget(main_view)
    
        # Apply stored GUI settings
        qsettings = QSettings("FYR", "WYSIWYG")
        zoom = int(qsettings.value("zoom_factor", 100))
        main_view.setZoomFactor(zoom / 100.0)
        font_size = int(qsettings.value("font_size", 12))
        main_view.settings().setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, font_size)
        font_family = qsettings.value("font_family", "Arial")
        main_view.settings().setFontFamily(QWebEngineSettings.FontFamily.StandardFont, font_family)
        main_page.windowCloseRequested.connect(main_window.close)
    
        # --- Native Windows Menu Bar ---
        menu_bar = main_window.menuBar()
    
        # File Menu
        file_menu = menu_bar.addMenu("&File")
        refresh_action = file_menu.addAction("&Refresh")
        refresh_action.triggered.connect(lambda: main_view.reload())
        update_menus_action = file_menu.addAction("&Update Menus")
        update_menus_action.triggered.connect(lambda: main_view.page().runJavaScript("document.getElementById('updateMenusBtn')?.click();"))
        file_menu.addSeparator()
        quit_action = file_menu.addAction("&Quit")
        quit_action.triggered.connect(main_window.close)
    
        # Tools Menu
        tools_menu = menu_bar.addMenu("&Tools")
        wysiscan_action = tools_menu.addAction("&Wysiscan")
        wysiscan_action.triggered.connect(lambda: main_view.page().runJavaScript("document.getElementById('runWysiScanBtn')?.click();"))
        walmart_action = tools_menu.addAction("&Walmart")
        walmart_action.triggered.connect(lambda: main_view.page().runJavaScript("document.getElementById('runWalmartSheetBtn')?.click();"))
        price_calc_action = tools_menu.addAction("&Price Calc")
        price_calc_action.triggered.connect(lambda: main_view.page().runJavaScript("document.getElementById('openCalcBtn')?.click();"))
        uberpaste_action = tools_menu.addAction("&UberPaste")
        uberpaste_action.triggered.connect(lambda: main_view.page().runJavaScript("document.getElementById('runUberPasteBtn')?.click();"))
    
        # View Menu
        view_menu = menu_bar.addMenu("&View")
        darkmode_action = view_menu.addAction("&Darkmode on/off")
        darkmode_action.triggered.connect(lambda: main_view.page().runJavaScript("document.getElementById('themeBtn')?.click();"))
        gui_adjust_action = view_menu.addAction("&Gui Adjust")
        gui_adjust_action.triggered.connect(lambda: GuiAdjustDialog(main_window, main_view).exec())
    
        # Admin Menu
        admin_menu = menu_bar.addMenu("&Admin")
        editor_action = admin_menu.addAction("&Editor")
        editor_action.triggered.connect(lambda: main_view.page().runJavaScript("document.getElementById('editorBtn')?.click();"))
    
        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction("&Change Log")
        help_menu.addAction("&About")
    
        # Periodic synchronization of button states
        def update_menu_states():
            js = """
            (function() {
                return {
                    wysiscan: !!document.getElementById('runWysiScanBtn')?.disabled,
                    uberpaste: !!document.getElementById('runUberPasteBtn')?.disabled,
                    walmart: !!document.getElementById('runWalmartSheetBtn')?.disabled
                };
            })()
            """
            def on_result(res):
                if res:
                    wysiscan_action.setDisabled(res.get("wysiscan", False))
                    uberpaste_action.setDisabled(res.get("uberpaste", False))
                    walmart_action.setDisabled(res.get("walmart", False))
            main_view.page().runJavaScript(js, on_result)
        
        menu_timer = QTimer(main_window)
        menu_timer.setInterval(1000)
        menu_timer.timeout.connect(update_menu_states)
        menu_timer.start()
    
        if scrape_bridge:
            def on_scrape_triggered(url):
                main_window.showNormal()
                main_window.activateWindow()
                main_window.raise_()
                js = f"""
                (function() {{
                    const urlInput = document.getElementById('discogsUrlInput');
                    const scrapeBtn = document.getElementById('scrapeBtn');
                    if (urlInput && scrapeBtn) {{
                        urlInput.value = {json.dumps(url)};
                        urlInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        scrapeBtn.click();
                    }}
                }})();
                """
                main_view.page().runJavaScript(js)
            scrape_bridge.trigger_scrape.connect(on_scrape_triggered)
    
        def main_close_event(event):
            for name, proc in CHILD_PROCESSES.items():
                if proc and proc.poll() is None:
                    try:
                        logging.info(f"Terminating child process: {name}")
                        proc.terminate()
                        try:
                            proc.wait(timeout=2.0)
                        except subprocess.TimeoutExpired:
                            logging.warning(f"Process {name} did not exit on terminate. Killing it.")
                            proc.kill()
                            proc.wait()
                    except Exception as e:
                        logging.error(f"Error terminating {name}: {e}")
            event.accept()
        
        main_window.closeEvent = main_close_event
        main_window.show()
    
        exit_code = qt_app.exec()
    
        # Explicit cleanup to prevent profile deletion warnings
        main_view.setPage(None)
        main_page.setParent(None)
        del main_page
        del main_view
        del profile
    
        sys.exit(exit_code)

    else:
        # --- BROWSER MODE (default) ---
        # Server is already running on a daemon thread. Point a real browser at it.
        import webbrowser
        view_host = '127.0.0.1' if BIND_HOST == '0.0.0.0' else BIND_HOST
        url = f"http://{view_host}:8008"
        logging.info(f"Opening WYSIWYG in default browser at {url}")
        try:
            webbrowser.open(url)
        except Exception as e:
            logging.warning(f"Could not auto-open browser ({e}). Open {url} manually.")
        # Keep the process alive so the server thread keeps serving.
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            logging.info("Shutdown requested via keyboard interrupt.")
