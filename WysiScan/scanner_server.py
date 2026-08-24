import os
import sys
import subprocess
import urllib.parse
import threading
import time
import signal
import shutil
import json
import uvicorn
import webbrowser
from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Body
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import win32com.client
import pythoncom
import cv2
import numpy as np
from datetime import datetime
import httpx
import re
from PIL import Image
try:
    import pytesseract
except ImportError:
    pytesseract = None

if sys.platform == "win32":
    import winreg

# Determine paths for frozen (exe) vs script execution
if getattr(sys, 'frozen', False):
    # Running as a compiled exe (onefile or onedir)
    if hasattr(sys, '_MEIPASS'):
        # One-file build: assets are in a temporary _MEIPASS folder.
        bundle_dir = sys._MEIPASS
    else:
        # One-dir build: assets are in the same directory as the executable.
        bundle_dir = os.path.dirname(sys.executable)
    APP_DIR = os.path.dirname(sys.executable) # For user-generated files like config/scans
    ASSET_DIR = os.path.join(bundle_dir, "WysiScan") # For bundled assets like HTML
else:
    # Running as script
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ASSET_DIR = APP_DIR

def _load_main_env_file():
    """Load KEY=VALUE pairs from the main app's .env into os.environ (if not
    already set). Mirrors main.py's _load_env_file so the AI Prompt can read
    GEMINI_API_KEY from the .env that lives in the main app root folder.
    Falls back to a .env next to this scanner if run standalone."""
    candidates = []
    # Main app root: scanner_server.py lives in <main>/WysiScan, so go up TWO dirs total
    base = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(os.path.dirname(base), ".env"))
    # Also the scanner's own directory (standalone exe builds)
    candidates.append(os.path.join(base, ".env"))
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), ".env"))
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except OSError:
                pass
            break  # only load the first .env found


_load_main_env_file()

if pytesseract:
    # Attempt to locate Tesseract binary if not in PATH
    if shutil.which("tesseract") is None:
        tesseract_path = None
        
        # 1. Check Windows Registry (Windows only)
        if sys.platform == "win32":
            try:
                # Try HKLM first (common for all users)
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tesseract-OCR", 0, winreg.KEY_READ)
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                tesseract_path = os.path.join(install_path, "tesseract.exe")
            except FileNotFoundError:
                try:
                    # Fallback to HKCU (current user only install)
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tesseract-OCR", 0, winreg.KEY_READ)
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    winreg.CloseKey(key)
                    tesseract_path = os.path.join(install_path, "tesseract.exe")
                except FileNotFoundError:
                    tesseract_path = None # Not found in registry

        if tesseract_path and os.path.exists(tesseract_path):
             pytesseract.pytesseract.tesseract_cmd = tesseract_path
             logging.info(f"Found Tesseract via registry: {tesseract_path}")
        else:
            # 2. Check hardcoded paths as a fallback
            possible_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.join(APP_DIR, "Tesseract-OCR", "tesseract.exe"),
                os.path.join(APP_DIR, "tesseract.exe")
            ]
            
            # Check Local AppData (common for single-user installs)
            if os.environ.get('LOCALAPPDATA'):
                possible_paths.insert(2, os.path.join(os.environ['LOCALAPPDATA'], "Tesseract-OCR", "tesseract.exe"))

            for p in possible_paths:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    logging.info(f"Found Tesseract via fallback path: {p}")
                    break

SCAN_DIR = os.path.join(APP_DIR, "scans")
if not os.path.exists(SCAN_DIR):
    os.makedirs(SCAN_DIR)

TEMP_DIR = os.path.join(APP_DIR, "temp")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

CONFIG_FILE = os.path.join(APP_DIR, "config.json")

def cleanup_directory(directory, older_than=0):
    """
    Cleans up files in a directory.
    older_than: seconds. If 0, deletes all files.
    """
    if not os.path.exists(directory):
        return

    now = time.time()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file():
                    try:
                        if older_than == 0 or entry.stat().st_mtime < (now - older_than):
                            os.remove(entry.path)
                    except Exception as e:
                        logging.error(f"Failed to remove {entry.name}: {e}")
    except Exception as e:
        logging.error(f"Error scanning dir {directory}: {e}")

def cleanup_temp(older_than=0):
    cleanup_directory(TEMP_DIR, older_than)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Clean all temp files on startup
    cleanup_temp(older_than=0)
    
    # Start periodic cleanup task
    def periodic_cleanup():
        while True:
            time.sleep(1800) # Check every 30 minutes
            cleanup_temp(older_than=3600) # Delete files older than 1 hour
            
    threading.Thread(target=periodic_cleanup, daemon=True).start()
    yield
    # Cleanup on shutdown
    cleanup_temp(older_than=0)
    cleanup_directory(SCAN_DIR, older_than=0)

def get_backup_path_in_temp(original_path, level=1):
    """Generates a unique path for a backup file in the TEMP_DIR."""
    # Sanitize the original path to create a valid filename.
    # This ensures "C:\scans\a.jpg" and "D:\scans\a.jpg" have different backup names.
    sanitized_path = re.sub(r'[:\\/]', '_', original_path)
    backup_filename = f"{sanitized_path}.bak"
    if level > 1:
        backup_filename += str(level)
    return os.path.join(TEMP_DIR, backup_filename)

def get_redo_path_in_temp(original_path):
    """Generates a unique path for a redo file in the TEMP_DIR."""
    sanitized_path = re.sub(r'[:\\/]', '_', original_path)
    return os.path.join(TEMP_DIR, f"{sanitized_path}.redo")

def create_backup(file_path):
    """Creates a .bak copy of a file before it's modified in the temp dir, with rotation."""
    if not file_path or not os.path.exists(file_path):
        return

    max_undo = 5 # Number of undo levels
    
    if os.path.abspath(file_path) == os.path.abspath(get_backup_path_in_temp(file_path, 1)):
        logging.error(f"Attempted to create backup where source and destination are identical: {file_path}")
        return # Prevent copying a file onto itself

    # First, rotate existing backups up one level
    # e.g., .bak4 -> .bak5, .bak3 -> .bak4, etc.
    # We must do this in reverse to avoid overwriting.
    for i in range(max_undo, 1, -1):
        src_path = get_backup_path_in_temp(file_path, i - 1)
        dest_path = get_backup_path_in_temp(file_path, i)
        if os.path.exists(src_path):
            if os.path.exists(dest_path):
                os.remove(dest_path) # Remove old .bak5
            shutil.move(src_path, dest_path)

    # Now, create the new primary backup (.bak)
    primary_backup_path = get_backup_path_in_temp(file_path, 1)
    try:
        shutil.copy2(file_path, primary_backup_path)
        logging.info(f"Created backup for {file_path} at {primary_backup_path}")
    except Exception as e:
        logging.error(f"Failed to create backup for {file_path}: {e}")

app = FastAPI(lifespan=lifespan)

def get_prompt_file_path():
    candidates = [
        os.path.join(APP_DIR, "default_prompt.json"),
        os.path.join(ASSET_DIR, "default_prompt.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_prompt.json"),
        os.path.join(os.getcwd(), "WysiScan", "default_prompt.json")
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None

# 1. Endpoint to retrieve default prompt JSON
@app.get('/get-default-prompt')
async def get_default_prompt():
    prompt_file = get_prompt_file_path()
    if prompt_file and os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                try:
                    data = json.loads(content)
                except Exception:
                    data = {"default_prompt": content}
            return {'status': 'success', 'prompt': data}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    return {'status': 'error', 'message': 'default_prompt.json not found'}

# 2. Endpoint to run CLI command with prompt and images
@app.post('/run-cli-prompt')
async def run_cli_prompt(data: dict = Body(default={})):
    prompt = data.get('prompt', '')
    files = data.get('files', [])

    if not prompt:
        return {'status': 'error', 'message': 'No prompt provided.'}
    if not files or len(files) < 1 or len(files) > 5:
        return {'status': 'error', 'message': 'Select between 1 and 5 files.'}

    # Determine model from default_prompt.json if available
    model_name = "gemini-3.6-flash"
    prompt_file = get_prompt_file_path()
    if prompt_file and os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as pf:
                pj = json.load(pf)
                if isinstance(pj, dict) and pj.get("model"):
                    model_name = pj["model"]
        except Exception:
            pass

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        try:
            cfg = load_config()
            api_key = cfg.get("gemini_api_key") or cfg.get("google_api_key")
        except Exception:
            pass
#   -------------------------
#   -------------------------

    try:
        from google import genai
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
        
        contents = [prompt]
        for f in files:
            if os.path.exists(f):
                contents.append(Image.open(f))

        # Retry setup for temporary 503 capacity spikes
        max_retries = 3
        base_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries} using model: {model_name}")
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents
                )
                return {'status': 'success', 'output': response.text or ""}
            except Exception as err:
                err_msg = str(err)
                print(f"DEBUG - Attempt {attempt + 1} failed: {err_msg}")

                # If it's a 503 high-demand spike, wait and retry
                if "503" in err_msg and attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)
                    print(f"Server busy (503). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise err
    except Exception as sdk_err:
        print(f"DEBUG - Python SDK Error (Final): {sdk_err}")
        try:
            cmd = ["npx", "-y", "@google/gemini-cli", prompt] + files
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=True,
                timeout=120
            )
            output = result.stdout if result.stdout else result.stderr
            if output:
                return {'status': 'success', 'output': output}
        except Exception:
            pass
        return {'status': 'error', 'message': f'AI prompt failed: {str(sdk_err)}'}



DISCOGS_TOKEN = "PzJscAOAJKspsQFlsvQTDChKjbnaWypCetHnoyGK" 
HEADERS = {"User-Agent": "WysiScan-OCR/1.0", "Authorization": f"Discogs token={DISCOGS_TOKEN}"}

def resource_path_for_data(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller.
        This is specifically for finding data files in the main app directory.
    """
    if getattr(sys, 'frozen', False):
        # In a frozen app, the executable is in the root, where data.json should be.
        base_path = os.path.dirname(sys.executable)
        return os.path.join(base_path, relative_path)
    else:
        # In dev mode, scanner_server.py is in a sub-directory. Go up to find data.json.
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

def load_json_data(filename):
    path = resource_path_for_data(filename)
    if not os.path.exists(path):
        print(f"Warning: {filename} not found at {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return None

def format_discogs_data(data):
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
        grouped_by_cat = {}
        cat_order = []
        for item in temp_labels:
            cat_key = item.get('cat')
            if not cat_key: cat_key = 'N/A'
            
            if cat_key not in grouped_by_cat:
                grouped_by_cat[cat_key] = []
                cat_order.append(cat_key)
            grouped_by_cat[cat_key].append(item['name'])

        parts = []
        for cat in cat_order:
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
                if not first_group_cats:
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
    
    raw_formats = data.get('formats', [])
    
    def get_fmt_text_blob(fmt_list):
        blob = ""
        for f in fmt_list:
            blob += f.get('name', '') + " "
            blob += " ".join(f.get('descriptions', [])) + " "
            blob += (f.get('text', '') or "") + " "
        return blob

    all_blob = get_fmt_text_blob(raw_formats)
    
    # Simplified format string construction for OCR lookup
    # We can't rely on the complex block logic from main.py without more context
    # So we'll build a simpler, more direct format string.
    
    format_parts = []
    for f in raw_formats:
        name = f.get('name', '')
        qty = f.get('qty', '1')
        
        # Build the core format part
        part = ""
        if int(qty) > 1:
            part += f"{qty}x "
        part += name
        
        # Add descriptions
        descriptions = f.get('descriptions', [])
        if descriptions:
            part += ", " + ", ".join(descriptions)
            
        # Add free text
        text = f.get('text', '')
        if text:
            part += f" ({text})"
            
        format_parts.append(part)

    formats_str = " + ".join(format_parts)
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
    
    return raw_text_tool

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config_setting(key, value):
    config = load_config()
    config[key] = value
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except:
        pass

app.mount("/scans", StaticFiles(directory=SCAN_DIR), name="scans")

@app.get("/WysiScan.ico")
async def get_favicon_ico():
    return FileResponse(os.path.join(ASSET_DIR, "WysiScan.ico"))

@app.get("/WysiScan.png")
async def get_favicon_png():
    return FileResponse(os.path.join(ASSET_DIR, "WysiScan.png"))

def orient_cd_by_matrix_text(image_path):
    """
    Uses Tesseract's OSD to detect text orientation in the center of a CD
    and rotates the image accordingly. This is for correcting 90/180/270 degree rotations.
    """
    if not pytesseract:
        logging.warning("Pytesseract not available, skipping CD matrix orientation.")
        return False
    try:
        img = cv2.imread(image_path)
        if img is None:
            logging.error(f"Could not read image for OSD: {image_path}")
            return False

        # Isolate a central region where the matrix text is expected to be
        h, w = img.shape[:2]
        center_x, center_y = w // 2, h // 2
        # Use a 50% ROI to ensure we capture the matrix text
        roi_w, roi_h = int(w * 0.5), int(h * 0.5)
        x1, y1 = max(0, center_x - roi_w // 2), max(0, center_y - roi_h // 2)
        x2, y2 = min(w, x1 + roi_w), min(h, y1 + roi_h)
        roi = img[y1:y2, x1:x2]
        
        if roi.size == 0:
            logging.warning(f"CD matrix ROI is empty for OSD on {os.path.basename(image_path)}.")
            return False

        # Use Tesseract's Orientation and Script Detection (OSD)
        # --psm 0 is for Orientation and script detection (OSD) only.
        osd = pytesseract.image_to_osd(roi, config='--psm 0', output_type=pytesseract.Output.DICT)
        
        rotation = osd.get('rotate', 0)
        confidence = osd.get('orientation_conf', 0)
        
        logging.info(f"CD OSD for {os.path.basename(image_path)}: Angle={rotation}, Confidence={confidence:.2f}")

        # Only rotate if confidence is high enough and rotation is non-zero
        if confidence > 2.0 and rotation != 0: # Confidence threshold can be adjusted
            create_backup(image_path) # Backup before modifying
            rotated_img = cv2.rotate(img, {90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_CLOCKWISE}[rotation])
            cv2.imwrite(image_path, rotated_img)
            logging.info(f"Auto-rotated CD by {rotation} degrees based on matrix text.")
            return True # Indicate that a rotation happened
    except Exception as e:
        logging.error(f"Failed to orient CD by matrix text for {os.path.basename(image_path)}: {e}")
    return False

def auto_crop_image(image_path, output_path=None, padding=5, media_type="auto"):
    print(f"Auto-cropping: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        if output_path:
            shutil.copy(image_path, output_path)
            return output_path
        return image_path

    h_img, w_img = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if media_type == 'cd':
        # CD Matrix Mode: Adaptive Thresholding targets local shadows/text instead of large edges
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 10)
        connect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, connect_kernel)
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    else:
        # Normal Mode (Auto, Tape, LP): Gradient Thresholding targets massive structural blocks
        blurred = cv2.GaussianBlur(gray, (25, 25), 0)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        grad = cv2.morphologyEx(blurred, cv2.MORPH_GRADIENT, kernel)
        _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        connect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, connect_kernel)
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        print("No contours found.")
        if output_path:
            shutil.copy(image_path, output_path)
            return output_path
        return image_path

    # 6. Filter and Sort
    valid_contours = []
    for c in contours:
        area = cv2.contourArea(c)
        
        # Apply size constraints based on selected media type
        if media_type == 'cd':
            if area < (w_img * h_img * 0.0005) or area > (w_img * h_img * 0.5): continue
        elif media_type == 'tape':
            if area < (w_img * h_img * 0.02) or area > (w_img * h_img * 0.6): continue
        elif media_type == 'lp':
            if area < (w_img * h_img * 0.15): continue
        else:
            if area < (w_img * h_img * 0.001): continue
            
        valid_contours.append((area, c))
    
    # Sort by area descending
    valid_contours.sort(key=lambda x: x[0], reverse=True)
    
    if not valid_contours:
        print("No valid contours after filtering (all too small or too big).")
        if output_path:
            shutil.copy(image_path, output_path)
            return output_path
        return image_path
        
    # Take the largest valid contour
    best_cnt = valid_contours[0][1]

    # Heuristic: If the largest contour is very large (> 80% of image) likely due to 
    # rotation borders creating a 'scan bed' contour, and we have a second valid contour
    # that is significant (> 2%), prefer the second one as the actual object.
    if len(valid_contours) > 1:
        first_area = valid_contours[0][0]
        second_area = valid_contours[1][0]
        total_area = w_img * h_img
        
        if (first_area > 0.80 * total_area) and (second_area > 0.001 * total_area):
            print(f"Auto-crop: Skipping largest contour ({first_area/total_area:.1%}), picking second ({second_area/total_area:.1%})")
            best_cnt = valid_contours[1][1]

    # --- Background-subtraction fallback ---
    # Trigger if the gradient approach fails by capturing the whole bed (>85%), OR if it 
    # captures a massive reflection column causing the aspect ratio to break for CDs/LPs.
    run_fallback = False
    bx, by, bw, bh = cv2.boundingRect(best_cnt)
    if (bw * bh) > (w_img * h_img * 0.85):
        run_fallback = True
        
    if bw > 0 and bh > 0:
        ar = max(bw, bh) / min(bw, bh)
        if media_type == 'cd' and ar > 1.6:
            run_fallback = logging.info(f"Auto-crop fallback triggered: CD contour severely distorted (AR={ar:.2f})") or True
        elif media_type == 'lp' and ar > 1.3:
            run_fallback = logging.info(f"Auto-crop fallback triggered: LP contour severely distorted (AR={ar:.2f})") or True
        elif media_type == 'tape' and ar > 3.0:
            run_fallback = logging.info(f"Auto-crop fallback triggered: Tape contour severely distorted (AR={ar:.2f})") or True
        elif ar > 1.9:
            run_fallback = logging.info(f"Auto-crop fallback triggered: Generic contour severely distorted (AR={ar:.2f})") or True

    if run_fallback:
        s = max(10, min(30, h_img // 10, w_img // 10))
        corner_samples = [
            gray[:s, :s], gray[:s, w_img - s:],
            gray[h_img - s:, :s], gray[h_img - s:, w_img - s:]
        ]
        bg_brightness = float(np.mean([c.mean() for c in corner_samples]))

        if bg_brightness < 100:
            # Dark scanner bed: find pixels meaningfully brighter than background
            tval = int(min(255, max(bg_brightness * 2.0 + 20, 30)))
            _, fb_mask = cv2.threshold(gray, tval, 255, cv2.THRESH_BINARY)
            logging.info(f"Auto-crop fallback: dark bg ({bg_brightness:.0f}), threshold>{tval}")
        else:
            # Light scanner bed: find pixels meaningfully darker than background
            tval = int(max(0, min(bg_brightness * 0.7 - 10, 210)))
            _, fb_mask = cv2.threshold(gray, tval, 255, cv2.THRESH_BINARY_INV)
            logging.info(f"Auto-crop fallback: light bg ({bg_brightness:.0f}), threshold<{tval}")

        # Close small gaps so nearby content regions merge into one blob
        fb_close = cv2.morphologyEx(
            fb_mask, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        )
        fb_cnts, _ = cv2.findContours(fb_close, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        fb_valid = sorted(
            [(cv2.contourArea(c), c) for c in fb_cnts
             if (w_img * h_img * 0.001) < cv2.contourArea(c)],
            key=lambda x: x[0], reverse=True
        )
        if fb_valid:
            fb_x, fb_y, fb_w, fb_h = cv2.boundingRect(fb_valid[0][1])
            # Only accept the fallback if it produces a genuinely tighter crop
            if (fb_w * fb_h) < (bw * bh * 0.99):
                best_cnt = fb_valid[0][1]
                print(f"Auto-crop: background-subtraction fallback applied "
                      f"(bg={bg_brightness:.0f}, new_area={fb_w * fb_h / (w_img * h_img):.1%})")

    # 7. Bounding Box
    final_x, final_y, final_w, final_h = cv2.boundingRect(best_cnt)
    
    # 8. Padding (Ensure we don't go out of bounds or create empty/invalid images)
    try:
        pad = int(padding)
    except (ValueError, TypeError):
        pad = 5
        
    w = final_w + (pad * 2)
    h = final_h + (pad * 2)
    
    # If padding makes the crop box negative or empty, fall back to the unpadded bounding box
    if w <= 0 or h <= 0:
        x, y, w, h = final_x, final_y, final_w, final_h
    else:
        x = max(0, final_x - pad)
        y = max(0, final_y - pad)
        w = min(w_img - x, final_w + (pad * 2))
        h = min(h_img - y, final_h + (pad * 2))
        
        # If clipping to the image border makes it empty, fall back
        if w <= 0 or h <= 0:
            x, y, w, h = final_x, final_y, final_w, final_h
            
    cropped = img[y:y+h, x:x+w]
    
    # Save cropped image
    if output_path:
        save_path = output_path
    else:
        filename = f"crop_{os.path.basename(image_path)}"
        save_path = os.path.join(os.path.dirname(image_path), filename)
        
    cv2.imwrite(save_path, cropped)
    
    return save_path

@app.get("/")
async def index():
    # Read the HTML file
    path = os.path.join(ASSET_DIR, "scanner_test.html")
    if not os.path.exists(path):
        return HTMLResponse("Error: scanner_test.html not found")
        
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    return HTMLResponse(content)

@app.get("/config")
async def get_config():
    return load_config()

# ---------------------------------------------------------------------------
# Native Python dialog helper
# ---------------------------------------------------------------------------
# PowerShell takes 1-3 seconds to launch and its COM apartment threading causes
# instability (IUnknown exceptions) when run from FastAPI.
# 
# Our new solution uses a lightning-fast Python subprocess (using the same python
# executable as the server) with Tkinter. By running it in a subprocess, we
# isolate the Tkinter GUI event loop from FastAPI's async event loop.
# Most importantly, root.wm_attributes('-topmost', 1) instructs the Windows
# compositor to unconditionally render the dialog above all other windows,
# completely bypassing Windows 11 focus-stealing prevention.

def _run_py_dialog(script: str) -> str:
    """Run a Python script in an isolated subprocess to show a dialog."""
    try:
        # Set an environment variable so the sub-instance of WYSIWYG.exe 
        # knows to act as a dialog runner and skip server startup/cleanup.
        env = os.environ.copy()
        env["WYSIWYG_DIALOG_MODE"] = "true"

        logging.info(f"Launching Tkinter dialog via: {sys.executable}")
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, 
            creationflags=0x08000000, 
            check=True,
            env=env
        )
        if result.stderr:
            logging.warning(f"Tkinter dialog subprocess stderr: {result.stderr}")
        logging.info(f"Tkinter dialog subprocess stdout: {result.stdout.strip()}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Tkinter dialog subprocess failed with exit code {e.returncode}. Stderr: {e.stderr}")
        raise # Re-raise to be caught by the /browse-file endpoint
    except Exception as e:
        logging.error(f"Error running Tkinter dialog subprocess: {e}", exc_info=True)
        raise # Re-raise to be caught by the /browse-file endpoint

@app.post("/browse-folder")
def browse_folder(data: dict = Body(default={})):
    try:
        current_path = data.get("path")
        config_key = data.get("config_key", "save_location")
        
        # Build the python script for the subprocess
        script = [
            "import tkinter as tk",
            "from tkinter import filedialog",
            "import sys",
            "root = tk.Tk()",
            "root.withdraw()",
            "root.wm_attributes('-topmost', 1)",
            "kwargs = {'parent': root, 'title': 'Select Location'}"
        ]
        if current_path and os.path.isdir(current_path):
            escaped = current_path.replace("\\", "\\\\").replace("'", "\\'")
            script.append(f"kwargs['initialdir'] = '{escaped}'")
            
        script.append("path = filedialog.askdirectory(**kwargs)")
        script.append("if path: print(path)")

        path = _run_py_dialog("\n".join(script)).strip()
        
        # Tkinter returns forward slashes, normalize to backslashes for Windows
        if path:
            path = os.path.normpath(path)
            if config_key:
                save_config_setting(config_key, path)
            return {"status": "success", "path": path}
        return {"status": "cancelled"}
    except Exception as e:
        logging.error(f"Error in /browse-folder endpoint: {e}", exc_info=True) # Add logging here
        return {"status": "error", "message": str(e)}

@app.post("/browse-file")
def browse_file():
    try:
        script = [
            "import tkinter as tk",
            "from tkinter import filedialog",
            "import sys",
            "root = tk.Tk()",
            "root.withdraw()",
            "root.wm_attributes('-topmost', 1)",
            "paths = filedialog.askopenfilenames(",
            "    parent=root, title='Select Images',",
            "    filetypes=[('Image Files', '*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff')]",
            ")",
            "for p in root.tk.splitlist(paths):",
            "    if p: print(p)"
        ]
        
        stdout = _run_py_dialog("\n".join(script))
        # Tkinter returns forward slashes, normalize to backslashes
        paths = [os.path.normpath(p.strip()) for p in stdout.strip().splitlines() if p.strip()]
        
        if paths:
            return {"status": "success", "paths": paths}
        return {"status": "cancelled"}
    except Exception as e:
        logging.error(f"Error in /browse-file endpoint: {e}", exc_info=True) # Add logging here
        return {"status": "error", "message": str(e)}

@app.post("/update-config")
async def update_config(data: dict = Body(...)):
    for key, value in data.items():
        save_config_setting(key, value)
    return {"status": "success"}

@app.post("/batch-convert")
async def batch_convert(data: dict = Body(...)):
    source_folder = data.get("source_folder")
    output_folder = data.get("output_folder")
    format_type = data.get("format", "jpg")
    width = data.get("width")
    height = data.get("height")
    
    if not source_folder or not os.path.exists(source_folder):
        return {"status": "error", "message": "Source folder does not exist"}
        
    if not output_folder:
        output_folder = source_folder
        
    # Build command
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable, "--imageconvert"]
    else:
        python_exe = sys.executable
        if python_exe.endswith('pythonw.exe'):
            python_exe = python_exe.replace('pythonw.exe', 'python.exe')
        script_path = os.path.join(ASSET_DIR, "imageconvert", "app.py")
        cmd = [python_exe, script_path]
        
    cmd.extend([
        "--source", source_folder, 
        "--output", output_folder, 
        "--format", format_type,
        "--scale", "proportional"
    ])
    
    if width:
        cmd.extend(["--width", str(width)])
    if height:
        cmd.extend(["--height", str(height)])
        
    try:
        creationflags = 0
        if os.name == 'nt':
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            
        logging.info(f"Launching batch convert CLI: {cmd}")
        # Run blocking synchronous call
        res = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            creationflags=creationflags, 
            check=True
        )
        logging.info(f"Batch convert CLI success. Stdout: {res.stdout}")
        return {"status": "success", "message": "Batch conversion completed successfully."}
    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr or ""
        stdout_output = e.stdout or ""
        logging.error(f"Batch convert CLI subprocess failed: {e}\nStdout: {stdout_output}\nStderr: {stderr_output}")
        return {"status": "error", "message": f"Conversion failed: {e.stderr or str(e)}"}
    except Exception as e:
        logging.error(f"Batch convert CLI failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.post("/open-convert-gui")
async def open_convert_gui():
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable, "--imageconvert"]
    else:
        python_exe = sys.executable
        if python_exe.endswith('python.exe'):
            python_exe = python_exe.replace('python.exe', 'pythonw.exe')
        script_path = os.path.join(ASSET_DIR, "imageconvert", "app.py")
        cmd = [python_exe, script_path]
    
    try:
        logging.info(f"Launching GUI process: {cmd}")
        subprocess.Popen(cmd)
        return {"status": "success", "message": "Image converter GUI opened."}
    except Exception as e:
        logging.error(f"Failed to open GUI process: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.get("/view-image")
async def view_image(path: str):
    if os.path.exists(path):
        return FileResponse(path)
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        return FileResponse(path, headers=headers)
    return {"status": "error", "message": "File not found"}

@app.post("/trigger-scan")
async def trigger_scan(data: dict = Body(...)):
    group_name = data.get("group_name", "scan")
    scan_counter = data.get("scan_counter", 0)
    file_number = scan_counter + 1
    save_location = data.get("save_location")
    auto_delete_original = data.get("auto_delete_original", False)
    dpi = data.get("dpi", 300)  # Default DPI value
    crop_padding = data.get("crop_padding", 5)
    media_type = data.get("media_type", "auto")

    if save_location is not None:
        save_config_setting("save_location", save_location)
    save_config_setting("crop_padding", crop_padding)

    # Initialize reference holders for explicit COM release
    device_manager = None
    device_infos = None
    device_info = None
    scanner_device = None
    scan_item = None
    image = None
    prop = None
    final_path = None
    scan_success = False

    try:
        # Initialize COM library for this thread
        pythoncom.CoInitialize()

        try:
            device_manager = win32com.client.Dispatch("WIA.DeviceManager")
            
            # Load preferred scanner ID from config
            config = load_config()
            preferred_scanner_id = config.get("selected_scanner_id")
            
            scanner_device = None
            
            # Load scanner device infos
            device_infos = device_manager.DeviceInfos
            
            if preferred_scanner_id:
                # Try to find the exact scanner requested
                for device_info in device_infos:
                    if device_info.DeviceID == preferred_scanner_id:
                        try:
                            scanner_device = device_info.Connect()
                            logging.info(f"Connected to preferred scanner: {device_info.Properties('Name').Value}")
                            break
                        except Exception as e:
                            logging.warning(f"Failed to connect to preferred scanner {preferred_scanner_id}, falling back: {e}")
            
            if not scanner_device:
                # Fallback to the first available scanner device
                for device_info in device_infos:
                    if device_info.Type == 1:  # 1 for Scanner device type
                        try:
                            scanner_device = device_info.Connect()
                            logging.info(f"Connected to fallback scanner: {device_info.Properties('Name').Value}")
                            break
                        except Exception as e:
                            logging.warning(f"Failed to connect to scanner {device_info.Properties('Name').Value}: {e}")
            
            if not scanner_device:
                return {"status": "error", "message": "No scanner found. Please make sure it's connected and turned on."}

            # Check if Items exist
            if scanner_device.Items.Count == 0:
                 return {"status": "error", "message": "Scanner found but no scanning items (flatbed/ADF) were detected."}

            # Use the first scan item (usually the flatbed)
            scan_item = scanner_device.Items[1]

            # Set properties for color scan (Intent = 1)
            # 6146 is the PropertyID for "Current Intent"
            for prop in scan_item.Properties:
                if prop.PropertyID == 6146:
                    prop.Value = 1  # 1 for Color

            # Set DPI properties
            for prop in scan_item.Properties:
                if prop.Name == "HorizontalResolution":
                    prop.Value = dpi
                if prop.Name == "VerticalResolution":
                    prop.Value = dpi
            # Transfer the image as JPEG format
            image = scan_item.Transfer("{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}")
            
            if image:
                # Sanitize group_name to prevent path traversal or invalid characters
                safe_group_name = "".join(c for c in group_name if c.isalnum() or c in ('-', '_')).rstrip()
                if not safe_group_name:
                    safe_group_name = "scan"

                target_dir = SCAN_DIR
                if save_location and os.path.isdir(save_location):
                    target_dir = save_location

                final_filename = f"{safe_group_name}_{file_number}.jpg"
                final_path = os.path.join(target_dir, final_filename)
                
                temp_filename = f"temp_{safe_group_name}_{file_number}.jpg"
                temp_path = os.path.join(TEMP_DIR, temp_filename)
                
                # CRITICAL: WIA's SaveFile fails if the file already exists.
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                
                image.SaveFile(temp_path)
                
                if os.path.exists(temp_path):
                    # Copy the raw scan to the final path so processing only affects the destination file
                    shutil.copy2(temp_path, final_path)
                    scan_success = True
                
        except Exception as wia_error:
            logging.error(f"WIA Error during scan: {wia_error}")
            return {"status": "error", "message": f"WIA Error: {str(wia_error)}"}
        finally:
            # Explicitly release COM objects before CoUninitialize to prevent IUnknown release exceptions
            prop = None
            image = None
            scan_item = None
            scanner_device = None
            device_info = None
            device_infos = None
            device_manager = None
            pythoncom.CoUninitialize()
        
        if scan_success and final_path and os.path.exists(final_path):
            # For CDs, first try to orient by matrix text
            if media_type == 'cd':
                if pytesseract: # Only attempt if Tesseract is available
                    orient_cd_by_matrix_text(final_path)
                else:
                    logging.warning("Tesseract not available, skipping CD matrix orientation.")
            else: # For non-CD media types, perform auto-deskew
                perform_auto_deskew(final_path, padding=crop_padding)
            # The original temp_path is intentionally NOT deskewed to preserve the raw scan.

            # Process Auto-Crop
            cropped_path = auto_crop_image(final_path, output_path=final_path, padding=int(crop_padding), media_type=media_type)
            
            original_deleted = False
            if auto_delete_original:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                        original_deleted = True
                    except Exception:
                        pass

            # Return URL relative to mount
            response = {
                "status": "success", 
                "cropped": f"/view-image?path={urllib.parse.quote(cropped_path)}",
                "cropped_path": cropped_path,
                "original_deleted": original_deleted,
                "original": None,
                "original_path": None
            }
            if not original_deleted:
                response["original"] = f"/view-image?path={urllib.parse.quote(temp_path)}"
                response["original_path"] = temp_path
            
            return response
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    return {"status": "error", "message": "Scan cancelled or failed"}

@app.get("/list-scanners")
async def list_scanners():
    """Lists all available WIA scanner devices."""
    device_manager = None
    device_infos = None
    device_info = None
    try:
        pythoncom.CoInitialize()
        device_manager = win32com.client.Dispatch("WIA.DeviceManager")
        scanners = []

        device_infos = device_manager.DeviceInfos
        for device_info in device_infos:
            if device_info.Type == 1: # Scanner
                name = device_info.Properties("Name").Value
                scanners.append({
                    "id": device_info.DeviceID,
                    "name": name
                })
        
        config = load_config()
        selected_id = config.get("selected_scanner_id")
        
        return {"status": "success", "scanners": scanners, "selected_id": selected_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        device_info = None
        device_infos = None
        device_manager = None
        pythoncom.CoUninitialize()

@app.post("/set-scanner")
async def set_scanner(data: dict = Body(...)):
    """Sets the preferred scanner ID."""
    scanner_id = data.get("scanner_id")
    if not scanner_id:
        return {"status": "error", "message": "Scanner ID not provided."}
    
    save_config_setting("selected_scanner_id", scanner_id)
    return {"status": "success", "message": "Preferred scanner updated."}

@app.post("/import-file")
async def import_file(data: dict = Body(...)):
    source_path = data.get("source_path")
    group_name = data.get("group_name", "scan")
    scan_counter = data.get("scan_counter", 0)
    file_number = scan_counter + 1
    save_location = data.get("save_location")
    auto_delete_original = data.get("auto_delete_original", False)
    crop_padding = data.get("crop_padding", 5)
    media_type = data.get("media_type", "auto")

    if not source_path or not os.path.exists(source_path):
        return {"status": "error", "message": "Source file not found"}

    if save_location is not None:
        save_config_setting("save_location", save_location)
    save_config_setting("crop_padding", crop_padding)

    try:
        # Sanitize group_name
        safe_group_name = "".join(c for c in group_name if c.isalnum() or c in ('-', '_')).rstrip()
        if not safe_group_name:
            safe_group_name = "scan"

        target_dir = SCAN_DIR
        if save_location and os.path.isdir(save_location):
            target_dir = save_location

        final_filename = f"{safe_group_name}_{file_number}.jpg"
        final_path = os.path.join(target_dir, final_filename)
        
        temp_filename = f"temp_{safe_group_name}_{file_number}.jpg"
        temp_path = os.path.join(TEMP_DIR, temp_filename)
        
        # Copy source to temp path (simulating the scan result)
        shutil.copy(source_path, temp_path)
        
        # Copy the raw import to the final path so processing only affects the destination file
        shutil.copy2(temp_path, final_path)

        # For CDs, first try to orient by matrix text
        if media_type == 'cd':
            if pytesseract: # Only attempt if Tesseract is available
                orient_cd_by_matrix_text(final_path)
            else:
                logging.warning("Tesseract not available, skipping CD matrix orientation.")
        else: # For non-CD media types, perform auto-deskew
            perform_auto_deskew(final_path, padding=crop_padding)
        # The original temp_path is intentionally NOT deskewed to preserve the raw scan.

        # Process Auto-Crop
        cropped_path = auto_crop_image(final_path, output_path=final_path, padding=int(crop_padding), media_type=media_type)
        
        original_deleted = False
        if auto_delete_original:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    original_deleted = True
                except Exception:
                    pass

        # Return URL relative to mount
        response = {
            "status": "success", 
            "cropped": f"/view-image?path={urllib.parse.quote(cropped_path)}",
            "cropped_path": cropped_path,
            "original_deleted": original_deleted,
            "original": None,
            "original_path": None
        }
        if not original_deleted:
            response["original"] = f"/view-image?path={urllib.parse.quote(temp_path)}"
            response["original_path"] = temp_path
        
        return response
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/recrop")
async def recrop(data: dict = Body(...)):
    original_path = data.get("original_path")
    cropped_path = data.get("cropped_path")
    padding = data.get("padding", 5)
    media_type = data.get("media_type", "auto")

    if not original_path or not os.path.exists(original_path):
        return {"status": "error", "message": "Original file not found to recrop from."}
    
    if not cropped_path:
        return {"status": "error", "message": "No destination path for cropped image specified."}

    try:
        save_config_setting("crop_padding", int(padding))
        create_backup(cropped_path)
        # Re-run the auto-crop with the new padding, overwriting the old cropped file
        new_cropped_path = auto_crop_image(original_path, output_path=cropped_path, padding=int(padding), media_type=media_type)
        
        if new_cropped_path == cropped_path:
             return {"status": "success", "message": "Image recropped successfully."}
        else:
            return {"status": "error", "message": "Recrop process failed to produce the expected file."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/rotate-image")
async def rotate_image(data: dict = Body(...)):
    path = data.get("path")
    direction = data.get("direction") # 'left' or 'right'

    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}
    
    if direction not in ['left', 'right']:
        return {"status": "error", "message": "Invalid rotation direction"}

    try:
        create_backup(path)
        img = cv2.imread(path)
        if img is None:
            return {"status": "error", "message": "Could not read image file"}

        if direction == 'right':
            rotated_img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE) # Full rotation
        else: # left
            rotated_img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE) # Full counter rotation

        # Overwrite the existing file
        cv2.imwrite(path, rotated_img)
        
       # Add a cache-busting query parameter to the URL for the client
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={int(time.time())}"
        
        return {"status": "success", "message": "Image rotated", "new_url": new_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_image_background_color(img):
    """Samples the 4 corners of the image to determine the most common background color.
    Used to fill in borders seamlessly when rotating/deskewing images."""
    h, w = img.shape[:2]
    try:
        c1 = img[0:10, 0:10].mean(axis=(0,1))
        c2 = img[0:10, max(0, w-10):w].mean(axis=(0,1))
        c3 = img[max(0, h-10):h, 0:10].mean(axis=(0,1))
        c4 = img[max(0, h-10):h, max(0, w-10):w].mean(axis=(0,1))
        bg = (c1 + c2 + c3 + c4) / 4.0
        return (int(bg[0]), int(bg[1]), int(bg[2]))
    except Exception:
        return (255, 255, 255) # Fallback to white if tiny image

@app.post("/rotate-image-fine")
async def rotate_image_fine(data: dict = Body(...)):
    path = data.get("path")
    direction = data.get("direction")  # 'left' or 'right'
    angle = 45  # Fixed rotation angle of 45 degrees

    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    if direction not in ['left', 'right']:
        return {"status": "error", "message": "Invalid rotation direction"}

    try:
        create_backup(path)
        img = cv2.imread(path)
        if img is None:
            return {"status": "error", "message": "Could not read image file"}

        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        if direction == 'right':
            rotation_matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)  # Negative for clockwise
        else:  # left
            rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0) # Positive for counter-clockwise

        bg_color = get_image_background_color(img)
        rotated_img = cv2.warpAffine(img, rotation_matrix, (w, h), borderValue=bg_color)

        cv2.imwrite(path, rotated_img)
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={int(time.time())}"

        return {"status": "success", "message": f"Image rotated {angle} degrees", "new_url": new_url}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/deskew-image")
async def deskew_image(data: dict = Body(...)):
    path = data.get("path")
    angle = data.get("angle", 0.0)
    padding = data.get("padding", 5)
    skip_crop = data.get("skip_crop", False)

    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    try:
        create_backup(path)
        img = cv2.imread(path)
        if img is None:
            return {"status": "error", "message": "Could not read image file"}

        # Get image center
        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)

        # Get rotation matrix
        M = cv2.getRotationMatrix2D(center, float(angle), 1.0)

        # To avoid black borders, we can calculate the new bounding box size
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])

        # compute the new bounding dimensions of the image
        newW = int((h * sin) + (w * cos))
        newH = int((h * cos) + (w * sin))

        # adjust the rotation matrix to take into account translation
        M[0, 2] += (newW / 2) - center[0]
        M[1, 2] += (newH / 2) - center[1]

        bg_color = get_image_background_color(img)
        rotated_img = cv2.warpAffine(img, M, (newW, newH), borderValue=bg_color)

        if skip_crop:
            cv2.imwrite(path, rotated_img)
        else:
            # Save rotated image to a temporary path and then re-crop it
            temp_rotated_path = os.path.join(TEMP_DIR, f"rotated_{os.path.basename(path)}")
            cv2.imwrite(temp_rotated_path, rotated_img)

            # Now, auto-crop this rotated image to remove the excess borders, overwriting the original file
            auto_crop_image(image_path=temp_rotated_path, output_path=path, padding=int(padding))
            os.remove(temp_rotated_path)

        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={int(time.time())}"
        return {"status": "success", "message": "Image deskewed", "new_url": new_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def perform_auto_deskew(path, padding=5):
    """
    Analyzes the image at 'path' for skew, rotates it if necessary,
    and overwrites 'path' with the corrected version.
    Creates a backup before modifying to allow Undo.
    """
    if not path or not os.path.exists(path):
        return False, "File not found"

    try:
        create_backup(path)
        img = cv2.imread(path)
        if img is None:
            return False, "Could not read image"

        # Preprocessing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (25, 25), 0)
        
        # Use Morphological Gradient to detect edges (robust against white background)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        grad = cv2.morphologyEx(blurred, cv2.MORPH_GRADIENT, kernel)
        _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        connect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, connect_kernel)
        
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
             return False, "No content detected."

        # Find largest contour
        c = max(contours, key=cv2.contourArea)
        
        # Determine skew angle
        rect = cv2.minAreaRect(c)
        angle = rect[-1]
        
        # Normalize angle to [-45, 45]
        if angle > 45:
            angle -= 90
        elif angle < -45:
            angle += 90
            
        if abs(angle) < 0.2:
             return True, "Already aligned."

        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        newW = int((h * sin) + (w * cos))
        newH = int((h * cos) + (w * sin))
        M[0, 2] += (newW / 2) - center[0]
        M[1, 2] += (newH / 2) - center[1]

        bg_color = get_image_background_color(img)
        rotated_img = cv2.warpAffine(img, M, (newW, newH), borderValue=bg_color)

        # Overwrite the file at 'path' with the rotated (but not yet cropped) version.
        cv2.imwrite(path, rotated_img)
        
        return True, f"Auto-aligned ({angle:.2f}°)"

    except Exception as e:
        logging.error(f"Auto-deskew error: {e}")
        return False, str(e)

@app.post("/auto-deskew")
async def auto_deskew(data: dict = Body(...)):
    path = data.get("path")
    padding = data.get("padding", 5)
    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    success, message = perform_auto_deskew(path, padding)
    
    if success or message == "Already aligned.":
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={int(time.time())}"
        return {"status": "success", "message": message, "new_url": new_url}
    else:
        return {"status": "error", "message": message}

@app.post("/manual-crop")
async def manual_crop(data: dict = Body(...)):
    path = data.get("path")
    crop_data = data.get("crop_data")

    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}
    
    if not crop_data:
        return {"status": "error", "message": "Crop data not provided"}

    try:
        create_backup(path)
        img = cv2.imread(path)
        if img is None:
            return {"status": "error", "message": "Could not read image"}

        # cropper.js data can be float, so cast to int
        x = int(crop_data['x'])
        y = int(crop_data['y'])
        w = int(crop_data['width'])
        h = int(crop_data['height'])

        # Ensure crop coordinates are within image bounds
        h_img, w_img = img.shape[:2]
        x = max(0, x)
        y = max(0, y)
        w = min(w_img - x, w)
        h = min(h_img - y, h)

        cropped_img = img[y:y+h, x:x+w]
        cv2.imwrite(path, cropped_img) # Overwrite the existing file
        return {"status": "success", "message": "Image cropped successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/manual-crop-as-new")
async def manual_crop_as_new(data: dict = Body(...)):
    path = data.get("path") # This is the original image path
    crop_data = data.get("crop_data") 
    group_name = data.get("group_name", "scan")
    scan_counter = data.get("scan_counter", 0)
    file_number = scan_counter + 1
    save_location = data.get("save_location")

    if not path or not os.path.exists(path):
        return {"status": "error", "message": "Source file not found"}
    
    if not crop_data:
        return {"status": "error", "message": "Crop data not provided"}

    try:
        # Determine target directory and new filename
        target_dir = SCAN_DIR
        if save_location and os.path.isdir(save_location):
            target_dir = save_location
        
        safe_group_name = "".join(c for c in group_name if c.isalnum() or c in ('-', '_')).rstrip()
        if not safe_group_name: safe_group_name = "scan"

        new_filename = f"{safe_group_name}_{file_number}.jpg"
        new_filepath = os.path.join(target_dir, new_filename)

        if os.path.exists(new_filepath):
            return {"status": "error", "message": f"File {new_filename} already exists. Counter mismatch."}

        # Perform the crop (same logic as /manual-crop)
        img = cv2.imread(path)
        if img is None: return {"status": "error", "message": "Could not read image"}

        x, y, w, h = int(crop_data['x']), int(crop_data['y']), int(crop_data['width']), int(crop_data['height'])
        h_img, w_img = img.shape[:2]
        x, y = max(0, x), max(0, y)
        w, h = min(w_img - x, w), min(h_img - y, h)

        cropped_img = img[y:y+h, x:x+w]
        cv2.imwrite(new_filepath, cropped_img)

        return { "status": "success", "message": "New cropped image created.", "cropped_path": new_filepath, "cropped_url": f"/view-image?path={urllib.parse.quote(new_filepath)}" }
    except Exception as e: 
        return {"status": "error", "message": str(e)}

@app.post("/manual-crop-replace")
async def manual_crop_replace(data: dict = Body(...)):
    source_path = data.get("source_path")
    target_path = data.get("target_path")
    crop_data = data.get("crop_data")

    if not source_path or not os.path.exists(source_path):
        return {"status": "error", "message": "Source file not found"}
    
    if not target_path:
        return {"status": "error", "message": "Target path not specified"}
    
    if not crop_data:
        return {"status": "error", "message": "Crop data not provided"}

    try:
        create_backup(target_path)
        img = cv2.imread(source_path)
        if img is None: return {"status": "error", "message": "Could not read source image"}

        x, y, w, h = int(crop_data['x']), int(crop_data['y']), int(crop_data['width']), int(crop_data['height'])
        h_img, w_img = img.shape[:2]
        x, y = max(0, x), max(0, y)
        w, h = min(w_img - x, w), min(h_img - y, h)

        cropped_img = img[y:y+h, x:x+w]
        cv2.imwrite(target_path, cropped_img)

        return {"status": "success", "message": "Image cropped and replaced successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/detect-bounds")
async def detect_bounds(data: dict = Body(...)):
    path = data.get("path")
    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    try:
        img = cv2.imread(path)
        if img is None:
            return {"status": "error", "message": "Could not read image"}

        h_img, w_img = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (25, 25), 0)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        grad = cv2.morphologyEx(blurred, cv2.MORPH_GRADIENT, kernel)
        _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        connect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, connect_kernel)
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return {"status": "success", "crop_data": None}

        valid_contours = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < (w_img * h_img * 0.001) or area > (w_img * h_img * 0.99):
                continue
            valid_contours.append((area, c))
        
        valid_contours.sort(key=lambda x: x[0], reverse=True)
        
        if not valid_contours:
            return {"status": "success", "crop_data": None}
            
        best_cnt = valid_contours[0][1]
        x, y, w, h = cv2.boundingRect(best_cnt)
        crop_data = {'x': x, 'y': y, 'width': w, 'height': h}
        
        return {"status": "success", "crop_data": crop_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/revert-crop")
async def revert_crop(data: dict = Body(...)):
    original_path = data.get("original_path")
    cropped_path = data.get("cropped_path")

    if not original_path or not os.path.exists(original_path):
        return {"status": "error", "message": "Original file not found."}
    
    if not cropped_path:
        return {"status": "error", "message": "Target path not specified."}

    try:
        create_backup(cropped_path)
        shutil.copy(original_path, cropped_path)
        return {"status": "success", "message": "Crop reverted to original."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _clean_bak_in_dir(directory):
    """Helper function to delete .bak files in a single directory."""
    deleted_count = 0
    errors = []
    if not directory or not os.path.isdir(directory):
        return
    
    logging.info(f"Scanning for backup files in: {directory}")
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                # Match files like .bak, .bak2, .bak10 etc. at the end of the filename
                if entry.is_file() and re.search(r'\.bak\d*$', entry.name):
                    try:
                        os.remove(entry.path)
                        deleted_count += 1
                        logging.info(f"Cleaned up backup file: {entry.path}")
                    except Exception as e:
                        error_msg = f"Failed to delete {entry.name}: {str(e)}"
                        errors.append(error_msg)
                        logging.error(error_msg)
    except Exception as e:
        error_msg = f"Error scanning directory {directory}: {str(e)}"
        errors.append(error_msg)
        logging.error(error_msg)

@app.post("/cleanup-backups")
async def cleanup_backups():
    """Deletes all .bak files from known scan locations."""
    config = load_config()
    save_location = config.get("save_location")
    
    # Use a set to clean each directory only once
    dirs_to_clean = {SCAN_DIR} 
    if save_location and os.path.isdir(save_location):
        dirs_to_clean.add(save_location)

    for directory in dirs_to_clean:
        _clean_bak_in_dir(directory)
    
    """Deletes all .bak files from the temp directory."""
    _clean_bak_in_dir(TEMP_DIR)
    return {"status": "success", "message": "Cleanup triggered."}

@app.post("/manage-files")
async def manage_files(data: dict = Body(...)):
    action = data.get("action")
    files = data.get("files", [])
    save_location = data.get("save_location")
    
    if not files:
        return {"status": "error", "message": "No files selected"}
        
    success_count = 0
    errors = []
    
    if action == "save":
        if save_location and os.path.isdir(save_location):
            saved_dir = save_location
        else:
            saved_dir = SCAN_DIR
            
        for file_path in files:
            try:
                if not os.path.exists(file_path):
                    continue

                filename = os.path.basename(file_path)
                dest_path = os.path.join(saved_dir, filename)

                img = cv2.imread(file_path)
                if img is None:
                    # Cannot process, just move if necessary
                    if os.path.abspath(file_path) != os.path.abspath(dest_path):
                        shutil.move(file_path, dest_path)
                    success_count += 1
                    continue

                # Resize logic
                h, w = img.shape[:2]
                target_size = 2200
                if max(h, w) != target_size:
                    scale = target_size / max(h, w)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
                    img = cv2.resize(img, (new_w, new_h), interpolation=interpolation)

                cv2.imwrite(dest_path, img)

                if os.path.abspath(file_path) != os.path.abspath(dest_path):
                    os.remove(file_path)
                
                success_count += 1
            except Exception as e:
                errors.append(f"Failed to save {os.path.basename(file_path)}: {str(e)}")

    elif action == "delete":
        for file_path in files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    success_count += 1
            except Exception as e:
                errors.append(f"Failed to delete {os.path.basename(file_path)}: {str(e)}")
                
    elif action == "rename":
        new_name = data.get("new_name")
        if not new_name:
            return {"status": "error", "message": "No new name specified"}
        
        safe_new_name = "".join(c for c in new_name if c.isalnum() or c in ('-', '_')).rstrip()
        if not safe_new_name:
            return {"status": "error", "message": "Invalid new name"}

        if len(files) == 1:
            file_path = files[0]
            if os.path.exists(file_path):
                try:
                    dir_name = os.path.dirname(file_path)
                    _, ext = os.path.splitext(file_path)
                    new_filename = f"{safe_new_name}{ext}"
                    new_path = os.path.join(dir_name, new_filename)
                    
                    if os.path.abspath(file_path) == os.path.abspath(new_path):
                        # Same file name, treat as no-op success
                        success_count += 1
                    elif os.path.exists(new_path):
                        errors.append(f"Destination file already exists: {new_filename}")
                    else:
                        os.rename(file_path, new_path)
                        
                        for level in range(1, 10):
                            old_bak = get_backup_path_in_temp(file_path, level)
                            if os.path.exists(old_bak):
                                new_bak = get_backup_path_in_temp(new_path, level)
                                try:
                                    if os.path.exists(new_bak):
                                        os.remove(new_bak)
                                    os.rename(old_bak, new_bak)
                                except Exception as bak_err:
                                    logging.error(f"Failed to rename backup {old_bak}: {bak_err}")
                        
                        old_redo = get_redo_path_in_temp(file_path)
                        if os.path.exists(old_redo):
                            new_redo = get_redo_path_in_temp(new_path)
                            try:
                                if os.path.exists(new_redo):
                                    os.remove(new_redo)
                                os.rename(old_redo, new_redo)
                            except Exception as redo_err:
                                logging.error(f"Failed to rename redo {old_redo}: {redo_err}")
                        
                        success_count += 1
                except Exception as e:
                    errors.append(f"Failed to rename {os.path.basename(file_path)}: {str(e)}")
        else:
            for file_path in files:
                if os.path.exists(file_path):
                    try:
                        dir_name = os.path.dirname(file_path)
                        name, ext = os.path.splitext(os.path.basename(file_path))
                        
                        parts = name.rsplit('_', 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            number_suffix = f"_{parts[1]}"
                        else:
                            number_suffix = ""
                            
                        new_filename = f"{safe_new_name}{number_suffix}{ext}"
                        new_path = os.path.join(dir_name, new_filename)
                        
                        if os.path.abspath(file_path) == os.path.abspath(new_path):
                            # Same file name, treat as no-op success
                            success_count += 1
                        elif os.path.exists(new_path):
                            errors.append(f"Destination file already exists: {new_filename}")
                        else:
                            os.rename(file_path, new_path)
                            
                            for level in range(1, 10):
                                old_bak = get_backup_path_in_temp(file_path, level)
                                if os.path.exists(old_bak):
                                    new_bak = get_backup_path_in_temp(new_path, level)
                                    try:
                                        if os.path.exists(new_bak):
                                            os.remove(new_bak)
                                        os.rename(old_bak, new_bak)
                                    except Exception as bak_err:
                                        logging.error(f"Failed to rename backup {old_bak}: {bak_err}")
                            
                            old_redo = get_redo_path_in_temp(file_path)
                            if os.path.exists(old_redo):
                                new_redo = get_redo_path_in_temp(new_path)
                                try:
                                    if os.path.exists(new_redo):
                                        os.remove(new_redo)
                                    os.rename(old_redo, new_redo)
                                except Exception as redo_err:
                                    logging.error(f"Failed to rename redo {old_redo}: {redo_err}")
                            
                            success_count += 1
                    except Exception as e:
                        errors.append(f"Failed to rename {os.path.basename(file_path)}: {str(e)}")
                        
    return {"status": "success", "processed": success_count, "errors": errors}

@app.post("/open-folder")
async def open_folder(data: dict = Body(default={})):
    path = data.get("path", "")
    
    if "view-image?path=" in path:
        path = path.split("view-image?path=")[-1].split("&")[0]
    path = urllib.parse.unquote(path)
    
    if path and os.path.isfile(path):
        path = os.path.dirname(path)
        
    # If no path is provided, or it's not a valid directory, use the default scan directory
    if not path or not os.path.isdir(path):
        path = SCAN_DIR
        
    try:
        os.startfile(os.path.abspath(path))
        return {"status": "success", "message": f"Opened folder: {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/open-file")
async def open_file(data: dict = Body(...)):
    path = data.get("path", "")
    
    if "view-image?path=" in path:
        path = path.split("view-image?path=")[-1].split("&")[0]
    path = urllib.parse.unquote(path)
    
    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}
    try:
        # Use os.path.abspath to ensure startfile works correctly
        os.startfile(os.path.abspath(path))
        return {"status": "success", "message": f"Opened file: {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/get-groups")
async def get_groups(path: str = None):
    target_dir = path
    if not target_dir:
        config = load_config()
        target_dir = config.get("save_location", SCAN_DIR)
    
    if not target_dir or not os.path.exists(target_dir):
        return {"groups": {}}
    
    groups = {}
    try:
        with os.scandir(target_dir) as entries:
            for entry in entries:
                if entry.is_file():
                    name, ext = os.path.splitext(entry.name)
                    if ext.lower() not in ['.jpg', '.jpeg', '.png']:
                        continue
                    
                    if '_' in name:
                        parts = name.rsplit('_', 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            group_name = parts[0]
                            number = int(parts[1])
                            
                            if group_name not in groups:
                                groups[group_name] = 0
                            if number > groups[group_name]:
                                groups[group_name] = number
    except Exception as e:
        print(f"Error scanning groups: {e}")
        return {"groups": {}}
        
    return {"groups": groups}

@app.get("/get-group-images")
async def get_group_images(group_name: str, path: str = None):
    target_dir = path
    if not target_dir:
        config = load_config()
        target_dir = config.get("save_location", SCAN_DIR)

    if not target_dir or not os.path.exists(target_dir) or not group_name:
        return {"images": []}

    images = []
    # Sanitize group_name just in case, though it should be safe from the frontend
    safe_group_name = "".join(c for c in group_name if c.isalnum() or c in ('-', '_')).rstrip()
    
    try:
        with os.scandir(target_dir) as entries:
            for entry in entries:
                if entry.is_file():
                    name, ext = os.path.splitext(entry.name)
                    if ext.lower() not in ['.jpg', '.jpeg', '.png']:
                        continue
                    
                    # Check if the file belongs to the group
                    if name.startswith(f"{safe_group_name}_"):
                        parts = name.rsplit('_', 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            number = int(parts[1])
                            full_path = os.path.join(target_dir, entry.name)
                            images.append({
                                "path": full_path,
                                "url": f"/view-image?path={urllib.parse.quote(full_path)}",
                                "number": number
                            })
    except Exception as e:
        print(f"Error scanning for group images: {e}")
        return {"images": []}

    # Sort images by number, descending to show newest first in the gallery
    images.sort(key=lambda x: x['number'], reverse=True)
    
    return {"images": images}

def preprocess_image_for_ocr(image_path):
    """
    Preprocesses an image for Tesseract OCR:
    1. Grayscale
    2. Upscale if small (Tesseract needs ~30px height for chars)
    3. Denoising (instead of harsh thresholding)
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return Image.open(image_path)

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Upscale if the image is small (common with crops)
        h, w = gray.shape
        if h < 1000: 
            scale = 2
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Denoise to remove grain/noise which causes gibberish
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        return Image.fromarray(denoised)
    except Exception as e:
        logging.error(f"Preprocessing failed: {e}")
        return Image.open(image_path)

def parse_tracklist_from_text(text_lines):
    """
    Applies heuristics to find a tracklist in raw OCR text.
    """
    tracklist = []
    # This pattern looks for things like: A1, A-1, 1, B 2, etc. at the start of a line.
    track_pattern = re.compile(r'^\s*([A-Z][-\s]?\d{1,2}|\d{1,2})\s+.*', re.IGNORECASE)

    # Pass 1: Find a "Tracklist" header and then parse subsequent lines.
    tracklist_start_index = -1
    for i, line in enumerate(text_lines):
        if 'tracklist' in line.lower() or 'tracks' in line.lower():
            tracklist_start_index = i
            break
    
    if tracklist_start_index != -1:
        for line in text_lines[tracklist_start_index+1:]:
            line = line.strip()
            if track_pattern.match(line):
                tracklist.append(line)
            # If we hit a blank line after finding some tracks, assume the list is over.
            elif tracklist and not line:
                break
        if tracklist:
            return tracklist

    # Pass 2 (Fallback): If no header was found, just grab all lines that look like tracks.
    for line in text_lines:
        line = line.strip()
        if track_pattern.match(line):
            tracklist.append(line)
            
    return tracklist

def parse_artist_title_from_text(text):
    """
    Applies heuristics to guess the Artist and Title from raw OCR text.
    """
    lines = [line for line in text.split('\n') if line.strip()]
    if not lines:
        return None, None

    # Heuristic 1: Look for "ARTIST - TITLE" on one of the first few lines
    for line in lines[:3]:
        if ' - ' in line:
            parts = line.split(' - ', 1)
            # Basic sanity check: not too long, not just numbers
            if len(parts) == 2 and 1 < len(parts[0]) < 60 and 1 < len(parts[1]) < 80:
                if re.search('[a-zA-Z]', parts[0]) and re.search('[a-zA-Z]', parts[1]):
                    return parts[0].strip(), parts[1].strip()

    # Heuristic 2: Assume first line is artist, second is title
    if len(lines) >= 2:
        artist = lines[0].strip()
        title = lines[1].strip()
        # Sanity checks to avoid grabbing junk
        if 1 < len(artist) < 60 and 1 < len(title) < 80:
             if re.search('[a-zA-Z]', artist) and not re.match(r'^[A-Z]?\d{1,2}\s+', title):
                return artist, title

    return None, None

def analyze_cassette_shell(image_path, ocr_text):
    """
    Analyzes image and text to generate a cassette shell description.
    """
    try:
        img = cv2.imread(image_path)
        if img is None: return ""
        
        h, w = img.shape[:2]
        aspect = w / h if h > 0 else 0
        
        # Basic check: Cassettes are usually rectangular (approx 1.6 ratio)
        # Allow for some cropping variance.
        is_likely_cassette = (1.3 < aspect < 1.9) or (0.5 < aspect < 0.8)
        
        # Check for cassette keywords in text to confirm intent
        keywords = ["side 1", "side a", "side one", "dolby", "100", "50", "tape", "cassette"]
        text_lower = ocr_text.lower()
        has_keywords = any(k in text_lower for k in keywords)
        
        if not (is_likely_cassette or has_keywords):
            return "" # Probably not a cassette, don't clutter output

        # 1. Color Analysis (Sample edges to avoid label)
        margin = int(min(h, w) * 0.1)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.rectangle(mask, (0,0), (w,h), 255, -1)
        cv2.rectangle(mask, (margin, margin), (w-margin, h-margin), 0, -1)
        mean_val = cv2.mean(img, mask=mask)[:3]
        b, g, r = mean_val
        brightness = (r + g + b) / 3
        
        shell_color = "Unknown"
        shell_type = "Opaque / Solid"
        
        if brightness > 200: shell_color = "White"
        elif brightness > 160 and r > b + 10: shell_color = "Off-White / Cream"
        elif brightness < 60: shell_color = "Black"
        elif 80 < brightness < 160 and abs(r-g) < 15 and abs(g-b) < 15:
            shell_color = "Grey / Clear"
            shell_type = "Clear / Transparent (Check Visual)"
        else: shell_color = "Custom / Other"

        # 2. Text Features
        window_markers = [m for m in ["100", "50", "0"] if m in ocr_text]
        window_desc = f"Clear Window With {'-'.join(window_markers)} Markers" if window_markers else "Clear Window (No Markers Detected)"

        stamps = []
        made_in = re.search(r'(Made\s+in\s+[A-Za-z\.\s]+)', ocr_text, re.IGNORECASE)
        if made_in: stamps.append(made_in.group(1)[:25].strip().title())
        stamps_str = ", ".join(stamps) if stamps else "None Detected"

        # 3. Build Output Block
        lines = ["\n--- Cassette Shell Analysis (Beta) ---"]
        lines.append(f"Shell Type/Style: {shell_type}")
        lines.append(f"Shell Texture: (Visual Inspection Required)") # Placeholder
        lines.append(f"Timing Window: {window_desc}")
        lines.append(f"Shell Color: {shell_color}")
        lines.append(f"Ink Color: (Visual Inspection Required)") # Placeholder
        lines.append(f"Binding: (Visual Inspection Required)") # Placeholder
        lines.append(f"Stamps: {stamps_str}")
        
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"Cassette analysis error: {e}")
        return ""

@app.post("/ocr-and-lookup")
async def ocr_and_lookup(data: dict = Body(...)):
    if not pytesseract:
        return {"status": "error", "message": "The 'pytesseract' library is missing from the application bundle."}

    path = data.get("path")
    if not path or not os.path.exists(path):
        return {"status": "error", "message": "Image path is missing or invalid."}

    # --- Tesseract Logic ---
    logging.info("Using Tesseract OCR.")
    try:
        processed_img = preprocess_image_for_ocr(path)
        raw_ocr_text = pytesseract.image_to_string(processed_img)
        all_digits = re.sub(r'\D', '', raw_ocr_text)
        barcode_match = re.search(r'(\d{10,13})', all_digits)

        if barcode_match:
            barcode = barcode_match.group(1)
            try:
                async with httpx.AsyncClient() as client:
                    search_url = f"https://api.discogs.com/database/search?barcode={barcode}"
                    search_resp = await client.get(search_url, headers=HEADERS, timeout=10)
                    
                    if search_resp.status_code == 200:
                        search_data = search_resp.json()
                        if search_data.get("results"):
                            release_url = search_data["results"][0].get("resource_url")
                            if release_url:
                                release_resp = await client.get(release_url, headers=HEADERS, timeout=10)
                                if release_resp.status_code == 200:
                                    release_data = release_resp.json()
                                    scraped_text = format_discogs_data(release_data)
                                    # Append cassette analysis if applicable
                                    cassette_info = analyze_cassette_shell(path, raw_ocr_text)
                                    if cassette_info: scraped_text += "\n" + cassette_info
                                    return {"status": "success", "scraped_text": scraped_text}
            except Exception as e:
                logging.error(f"Discogs API lookup failed for barcode {barcode}: {e}")

        # Tesseract fallback text formatting
        artist, title = parse_artist_title_from_text(raw_ocr_text)
        tracklist = parse_tracklist_from_text(raw_ocr_text.split('\n'))
        final_text = f"--- OCR Fallback (No Discogs Match Found) ---\nArtist: {artist or '(Could not parse)'}\nTitle: {title or '(Could not parse)'}\n\n--- Tracklist ---\n"
        final_text += "\n".join(tracklist) if tracklist else "(Could not parse tracklist)"
        cassette_info = analyze_cassette_shell(path, raw_ocr_text)
        if cassette_info: final_text += "\n" + cassette_info
        return {"status": "success", "scraped_text": final_text}
            
    except pytesseract.TesseractNotFoundError:
        logging.error("TesseractNotFoundError caught. Tesseract is not installed or not in PATH.")
        error_msg = (
            "Tesseract OCR Not Found.\n\n"
            "Please install Tesseract OCR and ensure it's added to your system's PATH during installation.\n\n"
            "Alternatively, you can copy the 'Tesseract-OCR' folder from a working installation into the same directory as this application."
        )
        return {"status": "error", "message": error_msg}
    except Exception as e:
        logging.error(f"An unexpected error occurred during OCR: {e}", exc_info=True)
        return {"status": "error", "message": f"An unexpected error occurred during OCR: {str(e)}"}

@app.post("/undo-action")
async def undo_action(data: dict = Body(...)):
    path = data.get("path")
    if not path:
        return {"status": "error", "message": "File path not provided."}

    primary_backup_path = path + ".bak"
    primary_backup_path = get_backup_path_in_temp(path, 1)

    if not os.path.exists(primary_backup_path):
        return {"status": "error", "message": "No undo history found for this file."}

    try:
        # Create a REDO backup of the current state before we overwrite it with the undo
        redo_path = get_redo_path_in_temp(path)
        shutil.copy2(path, redo_path)

        # Restore the primary backup. The current version of the file is discarded.
        shutil.move(primary_backup_path, path)
        logging.info(f"Restored {path} from {primary_backup_path}")

        # Now, shift the remaining backups up to fill the gap.
        # Now, shift the remaining backups down to fill the gap.
        max_undo = 5
        for i in range(2, max_undo + 1):
            # We want to move .bak2 to .bak, .bak3 to .bak2, etc.
            source_bak_path = path + ".bak" + str(i)
            dest_bak_path = path + ".bak" + (str(i - 1) if (i - 1) > 1 else "")
            source_bak_path = get_backup_path_in_temp(path, i)
            dest_bak_path = get_backup_path_in_temp(path, i - 1)

            if os.path.exists(source_bak_path):
                shutil.move(source_bak_path, dest_bak_path)
        
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={int(time.time())}"
        
        return {"status": "success", "message": "Last action undone.", "new_url": new_url}
    except Exception as e:
        logging.error(f"Undo failed for {path}: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/redo-action")
async def redo_action(data: dict = Body(...)):
    path = data.get("path")
    if not path:
        return {"status": "error", "message": "File path not provided."}
    
    redo_path = get_redo_path_in_temp(path)
    if not os.path.exists(redo_path):
        return {"status": "error", "message": "No redo history found."}

    try:
        # To redo, we must back up the current state (which is the result of an undo) back into history
        create_backup(path)
        shutil.move(redo_path, path)
        
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={int(time.time())}"
        return {"status": "success", "message": "Redo successful.", "new_url": new_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}

LAST_HEARTBEAT = time.time()

@app.post("/api/heartbeat")
async def heartbeat():
    global LAST_HEARTBEAT
    LAST_HEARTBEAT = time.time()
    return {"status": "ok"}

@app.post("/exit")
async def exit_app():
    """Endpoint to gracefully shut down the server."""
    def shutdown_server():
        time.sleep(0.5) # Give a moment for the response to be sent
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=shutdown_server).start()
    return {"status": "success", "message": "Server is shutting down."}

def run_server():
    # --- LOGGING SETUP ---
    # Configure logging specifically for the scanner process.
    # We use force=True to ensure this config overrides any inherited from main.py
    log_path = os.path.join(APP_DIR, "wysiscan_debug.log")
    try:
        logging.basicConfig(
            handlers=[RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=5)],
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            force=True
        )
    except Exception:
        pass # Fallback if force=True isn't supported or fails

    logging.info("--- WysiScan Server Starting ---")

    # Start heartbeat monitor thread to auto-shutdown when browser tab is closed
    def monitor_heartbeat():
        global LAST_HEARTBEAT
        # Allow 15 seconds for browser to load and send initial heartbeat
        time.sleep(15)
        while True:
            time.sleep(2)
            if time.time() - LAST_HEARTBEAT > 60:
                logging.info("No heartbeat received for 60 seconds. Shutting down WysiScan server...")
                os.kill(os.getpid(), signal.SIGTERM)
                break

    threading.Thread(target=monitor_heartbeat, daemon=True).start()

    # Only open browser automatically if run as a standalone script
    if '--launched-by-main' not in sys.argv:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open("http://127.0.0.1:8010")

        threading.Thread(target=open_browser, daemon=True).start()
        
    try:
        # log_config=None is CRITICAL. It prevents uvicorn from trying to use the console,
        # which causes the "NoneType object has no attribute isatty" crash in frozen apps.
        uvicorn.run(app, host="127.0.0.1", port=8010, log_config=None)
    except Exception as e:
        logging.critical(f"WysiScan Server Crashed: {e}", exc_info=True)

if __name__ == "__main__":
    run_server()