import os
import sys
import subprocess
import urllib.parse
import threading
import time
import signal
import shutil
import json
import hashlib
import uvicorn
import webbrowser
from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Body, UploadFile, File, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import win32com.client
import pythoncom
import cv2
import numpy as np
from datetime import datetime
import httpx
import re
from PIL import Image

def _scanner_cfg_keys():
    """Pull any gemini/google API keys from the scanner's local config so the
    shared key pool can include them alongside .env and keys.txt."""
    try:
        cfg = load_config()
        ck = (cfg.get("gemini_api_key") or cfg.get("google_api_key") or "").strip()
        return [ck] if ck else []
    except Exception:
        return []

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

# Cache of the last few AI-Prompt (Extract Text) runs, keyed by the set of
# selected image file names. Lets the user reopen prior results for the same
# images without re-running the (slow/costly) AI call.
CLI_CACHE_FILE = os.path.join(APP_DIR, "cli_cache.json")
CLI_CACHE_MAX = 3


def imageconvert_available():
    """True when the Image Convert sub-app is present in this build."""
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        # Standalone scanner bundles it at <base>/imageconvert; the main WYSIWYG
        # build bundles the whole WysiScan folder at <base>/WysiScan.
        return (os.path.exists(os.path.join(base, "imageconvert", "app.py")) or
                os.path.exists(os.path.join(base, "WysiScan", "imageconvert", "app.py")))
    return os.path.exists(os.path.join(ASSET_DIR, "imageconvert", "app.py"))


def _cli_cache_key(files):
    """Stable key for a set of image paths: sorted basenames joined."""
    names = sorted(os.path.basename(f) for f in (files or []))
    return "||".join(names)


def load_cli_cache():
    """Return the cache list (newest last). Empty list on error."""
    try:
        if os.path.isfile(CLI_CACHE_FILE):
            with open(CLI_CACHE_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def save_cli_cache(entries):
    """Persist the cache list (trimmed to CLI_CACHE_MAX, newest last)."""
    try:
        entries = entries[-CLI_CACHE_MAX:]
        with open(CLI_CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_cli_cache_entry(files):
    """Return cached output string for these image files, or None."""
    key = _cli_cache_key(files)
    for entry in reversed(load_cli_cache()):
        if entry.get("key") == key and entry.get("output"):
            return entry["output"]
    return None


def upsert_cli_cache(files, output):
    """Store a result, moving/keeping it as the most recent entry."""
    key = _cli_cache_key(files)
    entries = [e for e in load_cli_cache() if e.get("key") != key]
    entries.append({
        "key": key,
        "files": [os.path.basename(f) for f in (files or [])],
        "output": output,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })
    save_cli_cache(entries)


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

SCAN_DIR = os.path.join(APP_DIR, "scans")
if not os.path.exists(SCAN_DIR):
    os.makedirs(SCAN_DIR)

TEMP_DIR = os.path.join(APP_DIR, "temp")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

THUMB_DIR = os.path.join(TEMP_DIR, "thumbs")
if not os.path.exists(THUMB_DIR):
    os.makedirs(THUMB_DIR)

# Thumbnails are a regenerable cache. The 1-hour temp sweep only removes files
# directly in temp\, so thumbs\ survives it, and the 30-minute periodic sweep
# never runs when the scanner is only opened for a few minutes - which is why
# the folder grew without bound. A weekly wipe is enough to keep it in check;
# the stamp lives inside the folder and is the one file the wipe keeps.
THUMB_CLEAN_STAMP = os.path.join(THUMB_DIR, ".last_clean")
THUMB_CLEAN_INTERVAL = 7 * 24 * 60 * 60

# --- Path safety for file-serving endpoints -------------------------------
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

def _is_image_file(path):
    try:
        return os.path.isfile(path) and os.path.splitext(path)[1].lower() in IMAGE_EXTS
    except Exception:
        return False

def _allowed_media_roots():
    roots = [TEMP_DIR, SCAN_DIR]
    try:
        cfg = load_config() or {}
        for key in ("save_location", "last_import_dir"):
            value = cfg.get(key)
            if isinstance(value, str) and value.strip():
                roots.append(value)
    except Exception:
        pass
    return [os.path.abspath(r) for r in roots if r]

def _is_under_allowed_root(path):
    try:
        target = os.path.abspath(path)
    except Exception:
        return False
    for root in _allowed_media_roots():
        try:
            if os.path.commonpath([target, root]) == root:
                return True
        except ValueError:
            continue
    return False

CONFIG_FILE = os.path.join(APP_DIR, "config.json")

def cleanup_directory(directory, older_than=0, keep=()):
    """
    Cleans up files in a directory.
    older_than: seconds. If 0, deletes all files.
    keep: file names to leave alone (e.g. the weekly-cleanup stamp).
    """
    if not os.path.exists(directory):
        return

    now = time.time()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file():
                    if keep and entry.name in keep:
                        continue
                    try:
                        if older_than == 0 or entry.stat().st_mtime < (now - older_than):
                            os.remove(entry.path)
                    except Exception as e:
                        logging.error(f"Failed to remove {entry.name}: {e}")
    except Exception as e:
        logging.error(f"Error scanning dir {directory}: {e}")

def cleanup_temp(older_than=0):
    cleanup_directory(TEMP_DIR, older_than)

def cleanup_thumbs(force=False):
    """Wipe the thumbnail cache at most once a week (or now, with force).

    Safe at any time: every thumbnail is regenerated from its source image on
    the next /thumb request. Called on startup as well as from the periodic
    loop, so a scanner that is only opened briefly still gets its weekly wipe.
    """
    now = time.time()
    try:
        last = os.path.getmtime(THUMB_CLEAN_STAMP)
    except OSError:
        last = 0
    if not force and last and (now - last) < THUMB_CLEAN_INTERVAL:
        return

    removed = 0
    try:
        with os.scandir(THUMB_DIR) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                if os.path.abspath(entry.path) == os.path.abspath(THUMB_CLEAN_STAMP):
                    continue
                try:
                    os.remove(entry.path)
                    removed += 1
                except OSError as e:
                    logging.error(f"Failed to remove thumbnail {entry.name}: {e}")
    except OSError as e:
        logging.error(f"Error scanning {THUMB_DIR}: {e}")
        return

    try:
        with open(THUMB_CLEAN_STAMP, "w", encoding="utf-8") as fh:
            fh.write(str(int(now)))
    except OSError:
        pass
    logging.info(f"Weekly thumbnail cleanup: removed {removed} file(s).")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Clean all temp files on startup
    cleanup_temp(older_than=0)
    # ...and the thumbnail cache if a week has passed
    cleanup_thumbs()

    # Start periodic cleanup task
    def periodic_cleanup():
        while True:
            time.sleep(1800) # Check every 30 minutes
            cleanup_temp(older_than=3600) # Delete files older than 1 hour
            cleanup_directory(THUMB_DIR, older_than=86400,
                              keep=(os.path.basename(THUMB_CLEAN_STAMP),)) # Stale thumbnails
            cleanup_thumbs() # Weekly wipe, no-op until due
            
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


@app.exception_handler(Exception)
async def _unhandled_exception_json(request: Request, exc: Exception):
    """Return JSON for unhandled errors so clients always see the real reason
    instead of an HTML 'Internal Server Error' page."""
    logging.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"{type(exc).__name__}: {exc}"},
    )


# Only the local app origins may call this API. The scanner page is normally
# served by this server (8010); the main app also mounts it statically (8008),
# which legitimately needs cross-origin access. Everything else is blocked so a
# random website cannot read local files or drive the filesystem APIs.
ALLOWED_ORIGINS = {
    "http://127.0.0.1:8008",
    "http://localhost:8008",
    "http://127.0.0.1:8010",
    "http://localhost:8010",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

@app.middleware("http")
async def block_cross_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse(status_code=403,
                            content={"status": "error", "message": "Cross-origin request blocked."})
    return await call_next(request)

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

# 1b. Endpoint to retrieve the selectable list of named prompts from prompts.json
def _format_prompt_text(prompt_obj):
    """Flatten a prompt object into a single prompt string for the text box /
    Gemini call. Supports the current plain shape {"prompt": [...lines...]}
    and legacy shapes (GLOBAL RULE / FORMATTING / RULES) for backward compat."""
    if not isinstance(prompt_obj, dict):
        return str(prompt_obj)
    # Current shape: a flat list of prompt lines
    if "prompt" in prompt_obj and isinstance(prompt_obj["prompt"], list):
        return "\n".join(str(line) for line in prompt_obj["prompt"])
    # Legacy shape
    parts = []
    gr = prompt_obj.get("GLOBAL RULE")
    if gr:
        parts.append("GLOBAL RULE:")
        if isinstance(gr, list):
            parts.extend([f"  {g}" for g in gr])
        else:
            parts.append(f"  {gr}")
    fmt = prompt_obj.get("FORMATTING")
    if fmt:
        parts.append(f"FORMATTING: {fmt}")
    rules = prompt_obj.get("RULES")
    if isinstance(rules, list):
        parts.append("RULES:")
        for r in rules:
            if isinstance(r, dict):
                step = r.get("Step", "")
                desc = r.get("Description", "")
                sub = r.get("SubGroup", "")
                instrs = r.get("Instructions", [])
                line = f"  Step {step}:"
                if sub:
                    line += f" [{sub}]"
                if desc:
                    line += f" {desc}"
                parts.append(line)
                if isinstance(instrs, list):
                    for i in instrs:
                        parts.append(f"    - {i}")
                elif instrs:
                    parts.append(f"    - {instrs}")
            else:
                parts.append(f"  {r}")
    return "\n".join(parts)

def get_prompts_file_path():
    """prompts.json location, preferring the app folder (writable, editable)
    and falling back to the bundled copy inside the PyInstaller bundle. If only
    the bundled copy exists it is seeded next to the app so edits persist."""
    user_path = os.path.join(APP_DIR, "prompts.json")
    if os.path.isfile(user_path):
        return user_path
    bundled = os.path.join(ASSET_DIR, "prompts.json")
    if os.path.isfile(bundled):
        try:
            if os.path.abspath(bundled) != os.path.abspath(user_path):
                import shutil
                shutil.copyfile(bundled, user_path)
                return user_path
        except Exception:
            pass
        return bundled
    return user_path


def load_prompts():
    """Load prompts.json. Supports two shapes:
       a) A dict of named prompts: {"Basic": {...}, "Detailed": {...}}
       b) A single flat prompt object with an "Option" key naming it.
    Returns dict: { name: prompt_object }."""
    path = get_prompts_file_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # Shape (a): every value is itself a dict (a prompt object)
    if data and all(isinstance(v, dict) for v in data.values()):
        return data
    # Shape (b): single flat prompt object
    name = data.get("Option") or "Basic"
    return {name: data}

@app.get('/get-prompts')
async def get_prompts():
    prompts = load_prompts()
    if not prompts:
        return {'status': 'error', 'message': 'prompts.json not found or empty'}
    return {
        'status': 'success',
        'names': list(prompts.keys()),
        'prompts': {name: _format_prompt_text(obj) for name, obj in prompts.items()},
    }


# 1c. Endpoint to save (overwrite/create) a named prompt in prompts.json
@app.post('/save-prompt')
async def save_prompt(data: dict = Body(default={})):
    name = (data.get('name') or '').strip()
    prompt_text = data.get('prompt', '')
    if not name:
        return {'status': 'error', 'message': 'No prompt name provided.'}
    if not prompt_text or not prompt_text.strip():
        return {'status': 'error', 'message': 'Prompt text is empty.'}
    # Only the "Custom" prompt may be saved/edited. Basic, Detailed, and any
    # other preset are read-only by design.
    if name != 'Custom':
        return {'status': 'error', 'message': 'Only the "Custom" prompt can be saved.'}

    path = get_prompts_file_path()
    prompts = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                prompts = json.load(f)
        except Exception:
            prompts = {}
    if not isinstance(prompts, dict):
        prompts = {}

    # Store as a plain list of lines (the editable shape)
    lines = [ln.rstrip() for ln in prompt_text.replace("\r\n", "\n").split("\n")]
    prompts[name] = {"prompt": lines}

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(prompts, f, indent=4, ensure_ascii=False)
        return {'status': 'success', 'message': f'Saved prompt "{name}".', 'names': list(prompts.keys())}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}



# 2. Endpoint to run CLI command with prompt and images
@app.post('/run-cli-prompt')
def run_cli_prompt(data: dict = Body(default={})):
    prompt = data.get('prompt', '')
    files = data.get('files', [])
    # "Re-Run" sends force=True so a cached result cannot mask a new request.
    force = bool(data.get('force', False))

    if not prompt:
        return {'status': 'error', 'message': 'No prompt provided.'}
    if not files or len(files) < 1 or len(files) > 8:
        return {'status': 'error', 'message': 'Select between 1 and 8 files.'}

    # If we already extracted these exact images, return the cached result
    # instead of re-running the (slow/costly) AI call.
    if not force:
        cached = get_cli_cache_entry(files)
        if cached is not None:
            return {'status': 'success', 'output': cached, 'cached': True}

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

    # --- Gemini via shared key+model pool (gemini_pool.py in app root) ---
    import sys as _sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    try:
        import gemini_pool
        text, info = gemini_pool.gemini_generate(
            prompt_text=prompt, image_paths=files, timeout=120,
            extra_config_keys=_scanner_cfg_keys())
    except Exception as e:
        logging.exception("run-cli-prompt failed")
        return {'status': 'error', 'message': f'AI request failed: {e}'}
    if text is None:
        detail = info.get('last_error') or ''
        msg = info.get('error', 'AI prompt failed.')
        return {'status': 'error', 'message': f'{msg} {detail}'.strip()}
    upsert_cli_cache(files, text)
    return {'status': 'success', 'output': text}


# 3. Endpoint to fetch cached AI-Prompt results for a given set of images,
#    so the Extract Text window can reopen prior data without re-running AI.
@app.post('/get-cli-cache')
async def get_cli_cache(data: dict = Body(default={})):
    files = data.get('files', [])
    output = get_cli_cache_entry(files)
    if output is not None:
        return {'status': 'hit', 'output': output}
    return {'status': 'miss'}


# 4. Endpoint to dump the Extract Text content into Notepad and bring it forward.
@app.post('/open-in-notepad')
def open_in_notepad(data: dict = Body(default={})):
    text = data.get('text', '') or ''
    try:
        out_path = os.path.join(APP_DIR, "cli_last_output.txt")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.startfile(out_path)  # opens with default .txt app (Notepad) and focuses it
        return {'status': 'success', 'path': out_path}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}





@app.post('/run-discogs-add')
async def run_discogs_add(request: Request):
    try:
        form = await request.form()
        uploads = form.getlist('images')
        if not uploads:
            return {'status': 'error', 'message': 'No images uploaded.'}

        # Persist uploaded images to a temp dir for Gemini.
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix='discogs_add_')
        saved_paths = []
        for up in uploads:
            if hasattr(up, 'filename') and hasattr(up, 'file'):
                dest = os.path.join(tmpdir, os.path.basename(up.filename) or f'img_{len(saved_paths)}.jpg')
                with open(dest, 'wb') as out:
                    content = await up.read()
                    out.write(content)
                saved_paths.append(dest)
            elif isinstance(up, str) and os.path.isfile(up):
                saved_paths.append(up)
        if not saved_paths:
            return {'status': 'error', 'message': 'Could not read uploaded images.'}

        # Load the extraction prompt (instructs Gemini on the expected schema).
        prompt_path = os.path.join(APP_DIR, 'discogs_extract_prompt.txt')
        if os.path.isfile(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as pf:
                extract_prompt = pf.read()
        else:
            extract_prompt = "Extract physical media data as JSON (title, artist, label, catalog numbers, barcode, matrix, credits, tracklist, etc.)."

        # Gemini extraction via shared key+model pool (gemini_pool.py).
        import sys as _sys
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        import gemini_pool
        text, info = gemini_pool.gemini_generate(
            prompt_text=extract_prompt, image_paths=saved_paths, timeout=120,
            extra_config_keys=_scanner_cfg_keys())
        if text is None:
            return {'status': 'error', 'message': info.get('error', 'Gemini extraction failed.')}
        raw = text

        # Strip markdown fences if present, then parse JSON.
        raw = raw.strip()
        if raw.startswith('```'):
            raw = raw.split('```', 2)[1]
            if raw.lower().startswith('json'):
                raw = raw[4:]
        try:
            extracted_data = json.loads(raw)
        except Exception as e:
            return {'status': 'error', 'message': f'Could not parse Gemini JSON: {e}', 'raw': raw[:500]}

        # Run the Discogs Add macro (imported from the main app's Adds folder).
        try:
            main_root = os.path.dirname(APP_DIR)
            adds_dir = os.path.join(main_root, 'Adds')
            if adds_dir not in sys.path:
                sys.path.insert(0, adds_dir)
            import importlib
            discogs_add_mod = importlib.import_module('discogs_add')
            importlib.reload(discogs_add_mod)
            result = discogs_add_mod.discogs_add_macro(extracted_data)
        except Exception as e:
            import traceback as _tb
            print("DEBUG - Discogs macro error:\n" + _tb.format_exc())
            return {'status': 'error', 'message': f'Macro failed: {e}'}

        return {'status': 'success', 'extracted': extracted_data, 'tables': result.get('tables', {})}
    except Exception as e:
        import traceback as _tb
        print("DEBUG - /run-discogs-add error:\n" + _tb.format_exc())
        return {'status': 'error', 'message': str(e)}


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

JPEG_SAVE_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, 97]
# OpenCV's default save subsamples colour 4:2:0, which smears red/blue detail:
# measured 28 dB PSNR on a real scan versus 42 dB at the same quality in 4:4:4.
# Scans get re-encoded by every step (crop, straighten, adjust, tilt), so the
# default is worth overriding everywhere.
_444 = getattr(cv2, "IMWRITE_JPEG_SAMPLING_FACTOR_444", None)
if _444 is not None:
    JPEG_SAVE_PARAMS += [cv2.IMWRITE_JPEG_SAMPLING_FACTOR, _444]


def _imwrite_image(path, img):
    """Save a scan without the colour smearing OpenCV's defaults cause."""
    if os.path.splitext(path)[1].lower() in (".jpg", ".jpeg"):
        cv2.imwrite(path, img, JPEG_SAVE_PARAMS)
    else:
        cv2.imwrite(path, img)


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
        
    _imwrite_image(save_path, cropped)
    
    return save_path

_INDEX_HTML_CACHE = None

@app.get("/")
async def index():
    global _INDEX_HTML_CACHE
    if _INDEX_HTML_CACHE is None:
        path = os.path.join(ASSET_DIR, "scanner_test.html")
        if not os.path.exists(path):
            return HTMLResponse("Error: scanner_test.html not found")
        with open(path, 'r', encoding='utf-8') as f:
            _INDEX_HTML_CACHE = f.read()
    return HTMLResponse(_INDEX_HTML_CACHE, headers={"Cache-Control": "no-store"})

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
        # --- FROZEN (standalone exe): there is no python.exe to run scripts with,
        # so re-launch ourselves in "dialog runner" mode and pass results via a file.
        if getattr(sys, 'frozen', False):
            import tempfile, uuid, runpy  # noqa: F401  (runpy used in __main__)
            token = uuid.uuid4().hex
            script_path = os.path.join(tempfile.gettempdir(), f"wysiscan_dialog_{token}.py")
            result_path = os.path.join(tempfile.gettempdir(), f"wysiscan_dialog_{token}.txt")
            with open(script_path, "w", encoding="utf-8") as fh:
                fh.write(script)
            logging.info("Launching Tkinter dialog via frozen dialog runner")
            subprocess.run(
                [sys.executable, "--run-script", script_path, "--run-result", result_path],
                creationflags=0x08000000,
                check=True,
            )
            stdout = ""
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as fh:
                    stdout = fh.read()
            for p in (script_path, result_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            return stdout

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
        # Start in the last folder used for import; otherwise "This PC" (no network probing).
        last_dir = ""
        try:
            cfg_dir = (load_config() or {}).get("last_import_dir") or ""
            if cfg_dir and os.path.isdir(cfg_dir):
                last_dir = cfg_dir
        except Exception:
            last_dir = ""

        script = [
            "import tkinter as tk",
            "from tkinter import filedialog",
            "import sys",
            "root = tk.Tk()",
            "root.withdraw()",
            "root.wm_attributes('-topmost', 1)",
            "kwargs = {'parent': root, 'title': 'Select Images'}"
        ]
        if last_dir:
            escaped = last_dir.replace("\\", "\\\\").replace("'", "\\'")
            script.append(f"kwargs['initialdir'] = '{escaped}'")
        else:
            script.append("kwargs['initialdir'] = '::{20D04FE0-3AEA-1069-A2D8-08002B30309D}'")
        script.extend([
            "paths = filedialog.askopenfilenames(",
            "    filetypes=[('Image Files', '*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff')],",
            "    **kwargs",
            ")",
            "for p in root.tk.splitlist(paths):",
            "    if p: print(p)"
        ])
        
        stdout = _run_py_dialog("\n".join(script))
        # Tkinter returns forward slashes, normalize to backslashes
        paths = [os.path.normpath(p.strip()) for p in stdout.strip().splitlines() if p.strip()]
        
        if paths:
            try:
                save_config_setting("last_import_dir", os.path.dirname(paths[0]))
            except Exception:
                pass
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
def batch_convert(data: dict = Body(...)):
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
        if not imageconvert_available():
            return {"status": "error",
                    "message": "Image Convert is not bundled in this standalone WysiScan build. Use the full WYSIWYG app for batch conversion."}
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
        if not imageconvert_available():
            return {"status": "error",
                    "message": "Image Convert is not bundled in this standalone WysiScan build. Use the full WYSIWYG app."}
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

def _thumb_cache_path(path, width):
    try:
        mtime = int(os.path.getmtime(path))
    except OSError:
        return None
    key = hashlib.md5(f"{os.path.abspath(path)}|{mtime}|{width}".encode("utf-8", "ignore")).hexdigest()
    return os.path.join(THUMB_DIR, f"{key}.jpg")

@app.get("/thumb")
def thumb(path: str, w: int = 220):
    """Small, disk-cached JPEG thumbnail for the gallery grid."""
    if not path or not _is_image_file(path):
        return JSONResponse(status_code=404, content={"status": "error", "message": "File not found"})
    try:
        width = max(80, min(int(w), 600))
    except Exception:
        width = 220

    thumb_path = _thumb_cache_path(path, width)
    try:
        fresh = thumb_path and os.path.exists(thumb_path)
        if not fresh or os.path.getmtime(thumb_path) < os.path.getmtime(path):
            with Image.open(path) as img:
                try:
                    from PIL import ImageOps
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass
                img.thumbnail((width, width), Image.LANCZOS)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(thumb_path, "JPEG", quality=82)
        return FileResponse(thumb_path, headers={"Cache-Control": "private, max-age=60"})
    except Exception as e:
        logging.warning(f"Thumbnail generation failed for {path}: {e}")
        return FileResponse(path)

@app.get("/view-image")
async def view_image(path: str):
    if not _is_image_file(path) or not _is_under_allowed_root(path):
        return JSONResponse(status_code=403,
                            content={"status": "error", "message": "File not allowed"})
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return FileResponse(path, headers=headers)

@app.post("/trigger-scan")
def trigger_scan(data: dict = Body(...)):
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
            # "CD/45 Front" (tape in config) straightens its text first; other
            # non-CD media get the plain auto-deskew. CDs are not deskewed.
            straighten_note = ""
            if media_type == 'tape':
                # Never let the straighten step take a scan down with it.
                try:
                    ok_s, msg_s = straighten_front_image(final_path, padding=crop_padding)
                    if ok_s and msg_s and msg_s != "Already level.":
                        straighten_note = msg_s
                except Exception as e:
                    logging.error(f"CD/45 Front: straighten raised ({e}) - scan continues")
            elif media_type != 'cd':
                perform_auto_deskew(final_path, padding=crop_padding)
            # The original temp_path is intentionally NOT deskewed to preserve the raw scan.

            # Process Auto-Crop
            cropped_path = auto_crop_image(final_path, output_path=final_path, padding=int(crop_padding), media_type=media_type)

            # The user's Default slider preset is applied to every finished scan.
            # A brand-new scan: any colour history left from an earlier file at
            # this path is meaningless, and the Default preset is about to add
            # a fresh one.
            _forget_adjustments(cropped_path)
            _plain_forget(cropped_path)
            _forget_adjustments(temp_path)
            _plain_forget(temp_path)
            apply_default_adjustments(cropped_path)
            
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
            if straighten_note:
                response["message"] = straighten_note
            
            return response
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    return {"status": "error", "message": "Scan cancelled or failed"}

@app.get("/list-scanners")
def list_scanners():
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
def import_file(data: dict = Body(...)):
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

        # "CD/45 Front" (tape in config) straightens its text first; other non-CD
        # media get the plain auto-deskew. CDs are not deskewed.
        if media_type == 'tape':
            try:
                straighten_front_image(final_path, padding=crop_padding)
            except Exception as e:
                logging.error(f"CD/45 Front: straighten raised ({e}) - import continues")
        elif media_type != 'cd':
            perform_auto_deskew(final_path, padding=crop_padding)
        # The original temp_path is intentionally NOT deskewed to preserve the raw scan.

        # Process Auto-Crop
        cropped_path = auto_crop_image(final_path, output_path=final_path, padding=int(crop_padding), media_type=media_type)

        # A newly imported file carries no colour history of its own.
        _forget_adjustments(cropped_path)
        _plain_forget(cropped_path)
        _forget_adjustments(temp_path)
        _plain_forget(temp_path)

        # The user's Default slider preset is applied to every finished scan.
        apply_default_adjustments(cropped_path)

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
def recrop(data: dict = Body(...)):
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
        _plain_forget(cropped_path)

        # Re-cropping rebuilds the file from the original, so the colour history
        # and the Default preset start over.
        _forget_adjustments(new_cropped_path)
        apply_default_adjustments(new_cropped_path)

        if new_cropped_path == cropped_path:
             return {"status": "success", "message": "Image recropped successfully."}
        else:
            return {"status": "error", "message": "Recrop process failed to produce the expected file."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/rotate-image")
def rotate_image(data: dict = Body(...)):
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
        _geometry_changed(path)
        _imwrite_image(path, rotated_img)
        
       # Add a cache-busting query parameter to the URL for the client
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        
        return {"status": "success", "message": "Image rotated", "new_url": new_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Manual image adjustments -------------------------------------------------
# Brightness / contrast / saturation / hue / tint. The scanner UI previews these
# with CSS filters (instant) and only bakes them on "Apply". Every value applied
# is remembered per file so "Remove All" can take just the colour back off again
# without touching rotation, tilt or crop.


# Slider presets live in config.json under "adjust_presets". "default" is baked
# into every finished scan; the two customs are loaded on demand and only baked
# when Apply is pressed. Both save themselves as the sliders move.
ADJUST_KEYS = ("brightness", "contrast", "saturation", "hue", "tint")
ADJUST_PRESETS = ("default", "custom1", "custom2")


def _adjust_presets():
    """Every preset slot, always fully populated so the page never sees gaps."""
    stored = (load_config() or {}).get("adjust_presets") or {}
    presets = {}
    for name in ADJUST_PRESETS:
        slot = stored.get(name) or {}
        presets[name] = {k: float(slot.get(k) or 0) for k in ADJUST_KEYS}
    return presets


def save_adjust_preset(name, values):
    if name not in ADJUST_PRESETS:
        name = "default"
    presets = _adjust_presets()
    presets[name] = {k: float(values.get(k) or 0) for k in ADJUST_KEYS}
    save_config_setting("adjust_presets", presets)
    return presets


def _unadjust_image(img, brightness=0.0, contrast=0.0, saturation=0.0, hue=0.0, tint=0.0):
    """Take back exactly what _adjusted_image() did, in reverse order.

    Only colour is touched, so rotation, tilt and crop survive - which is what
    "Remove All" has to do. Pixels that were clipped to black/white when the
    adjustment was applied cannot come back; everything else is recovered.
    """
    out = img.astype(np.float32)

    # Tint was applied last on the way in, so undo it first.
    if tint:
        shift = tint * 1.28
        out[..., 2] = np.clip(out[..., 2] - shift, 0, 255)   # R
        out[..., 1] = np.clip(out[..., 1] + shift, 0, 255)   # G
        out[..., 0] = np.clip(out[..., 0] - shift, 0, 255)   # B

    if saturation or hue:
        hsv = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
        if hue:
            hsv[..., 0] = (hsv[..., 0] - hue / 2.0) % 180.0
        if saturation:
            hsv[..., 1] = np.clip(hsv[..., 1] / max(1e-6, 1.0 + saturation / 100.0), 0, 255)
        out = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

    if brightness:
        out -= brightness * 1.28
    if contrast:
        out = (out - 128.0) / max(1e-6, 1.0 + contrast / 100.0) + 128.0

    return np.clip(out, 0, 255).astype(np.uint8)


# Colour baked into each file, oldest first, so "Remove All" can take it back
# off without a full restore (which would also throw away tilt and rotation).
_ADJUST_HISTORY = {}      # abspath -> [values dict, ...]

# The colour-free pixels, frozen just before the first adjustment lands. This is
# what "Remove All" restores: undoing the maths cannot bring back highlights that
# were clipped, so the real pre-colour image is kept instead.
_PLAIN_STATE = {}         # abspath -> {"generation": int, "angle": float}
_PLAIN_GENERATION = {}    # abspath -> int, bumped by every geometry edit


def _plain_path(image_path):
    safe = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.abspath(image_path))
    return os.path.join(TEMP_DIR, f"{safe}.plain")


def _geometry_changed(path):
    """Note that the pixels were moved/cropped - the colour-free copy is stale."""
    key = os.path.abspath(path)
    _PLAIN_GENERATION[key] = _PLAIN_GENERATION.get(key, 0) + 1


def _plain_snapshot(path):
    """Freeze the un-coloured pixels before an adjustment is written."""
    try:
        plain = _plain_path(path)
        if os.path.exists(plain):
            return
        shutil.copy2(path, plain)
        key = os.path.abspath(path)
        _PLAIN_STATE[key] = {
            "generation": _PLAIN_GENERATION.get(key, 0),
            "angle": float((_TILT_STATE.get(key) or {}).get("angle", 0.0)),
        }
    except Exception as e:
        logging.error(f"Could not keep the colour-free copy: {e}")


def _plain_forget(path):
    key = os.path.abspath(path)
    _PLAIN_STATE.pop(key, None)
    plain = _plain_path(path)
    if os.path.exists(plain):
        try:
            os.remove(plain)
        except OSError:
            pass


def _remember_adjustment(path, values):
    _ADJUST_HISTORY.setdefault(os.path.abspath(path), []).append(dict(values))


def _forget_adjustments(path):
    """Drop the colour history - the pixels no longer contain those values."""
    _ADJUST_HISTORY.pop(os.path.abspath(path), None)


def apply_default_adjustments(path):
    """Bake the Default preset into a finished scan. Never raises.

    This is what stops a dark scanner needing the same sliders every time: the
    values are applied once per scan, after cropping.
    """
    try:
        preset = _adjust_presets()["default"]
        if not any(abs(v) > 0.01 for v in preset.values()):
            return False
        img = cv2.imread(path)
        if img is None:
            return False
        create_backup(path)
        _plain_snapshot(path)
        _imwrite_image(path, _adjusted_image(img, **preset))
        _remember_adjustment(path, preset)
        active = ", ".join(f"{k}={v:g}" for k, v in preset.items() if v)
        logging.info(f"Image Adjust: applied the Default preset ({active}) to {os.path.basename(path)}")
        return True
    except Exception as e:
        logging.error(f"Default image adjustments failed ({e}) - scan continues")
        return False


def _adjusted_image(img, brightness=0.0, contrast=0.0, saturation=0.0, hue=0.0, tint=0.0):
    out = img.astype(np.float32)

    # Contrast around mid-grey, then brightness as a percentage of full scale.
    if contrast:
        out = (out - 128.0) * (1.0 + contrast / 100.0) + 128.0
    if brightness:
        out += brightness * 1.28
    out = np.clip(out, 0, 255)

    # Saturation + hue in HSV (OpenCV hue runs 0-179 for 0-360 degrees).
    if saturation or hue:
        hsv = cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
        if hue:
            hsv[..., 0] = (hsv[..., 0] + hue / 2.0) % 180.0
        if saturation:
            hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + saturation / 100.0), 0, 255)
        out = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

    # Tint: positive values push magenta (R+B up, G down), negative push green.
    if tint:
        shift = tint * 1.28
        out[..., 2] = np.clip(out[..., 2] + shift, 0, 255)  # R
        out[..., 1] = np.clip(out[..., 1] - shift, 0, 255)  # G
        out[..., 0] = np.clip(out[..., 0] + shift, 0, 255)  # B

    return np.clip(out, 0, 255).astype(np.uint8)


@app.post("/adjust-preset")
def adjust_preset_save(data: dict = Body(...)):
    """Remember a slider preset. Values save themselves from the page, so there
    is no separate Save step and no confirmation needed."""
    name = data.get("preset") or "default"
    values = data.get("values") or {}
    try:
        presets = save_adjust_preset(name, values)
        return {"status": "success", "presets": presets}
    except Exception as e:
        logging.error(f"adjust-preset failed: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/adjust-image")
def adjust_image(data: dict = Body(...)):
    path = data.get("path")
    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    values = {k: float(data.get(k) or 0) for k in
              ("brightness", "contrast", "saturation", "hue", "tint")}
    if not any(values.values()):
        return {"status": "error", "message": "No adjustment values supplied."}

    try:
        img = cv2.imread(path)
        if img is None:
            return {"status": "error", "message": "Could not read image file"}

        create_backup(path)
        _plain_snapshot(path)
        _imwrite_image(path, _adjusted_image(img, **values))
        _remember_adjustment(path, values)
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        return {"status": "success", "message": "Image adjusted", "new_url": new_url}
    except Exception as e:
        logging.error(f"adjust-image failed: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/adjust-image-reset")
def adjust_image_reset(data: dict = Body(...)):
    """Put the colour-free picture back, keeping rotation/tilt/crop.

    Preferred path: restore the snapshot taken just before the first adjustment.
    That is the real un-edited image - no clipped highlights, no rounding.
    Fallback: undo the recorded maths (used when the pixels were edited in a way
    the snapshot cannot follow, e.g. a 90 deg turn after the colour went on).
    """
    path = data.get("path")
    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    key = os.path.abspath(path)
    plain = _plain_path(path)
    snapshot = _PLAIN_STATE.get(key)

    try:
        if snapshot and os.path.exists(plain) and snapshot["generation"] == _PLAIN_GENERATION.get(key, 0):
            # Geometry is unchanged since the snapshot, except possibly a tilt:
            # rotations about the centre add up, so replay the difference.
            tilt = _TILT_STATE.get(key) or {}
            media_type = tilt.get("media_type", "auto")
            angle_now = float(tilt.get("angle", 0.0))
            delta = angle_now - float(snapshot.get("angle", 0.0))

            create_backup(path)
            _replace_file_atomically(plain, path)
            if abs(delta) > 0.05:
                # Replay the tilt that was applied after the snapshot. When the
                # colour went on before any tilt, the stored crop window can be
                # reused, which reproduces the exact framing of the tilted scan.
                reuse = tilt.get("crop_rect") if abs(float(snapshot.get("angle", 0.0))) < 0.05 else None
                _rotate_file_by(path, path, delta, padding=5, media_type=media_type,
                                crop_rect=reuse)
            _plain_forget(path)
            _forget_adjustments(path)
            logging.info(f"Remove All: restored the colour-free pixels of {os.path.basename(path)}"
                         + (f" (tilt replayed {delta:+.1f} deg)" if abs(delta) > 0.05 else ""))
            new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
            return {"status": "success", "message": "Colour adjustments removed", "new_url": new_url}

        # Fallback: no usable snapshot - undo the maths instead.
        history = _ADJUST_HISTORY.get(key) or []
        if not history:
            return {"status": "error",
                    "message": "No colour adjustments to remove for this image."}
        img = cv2.imread(path)
        if img is None:
            return {"status": "error", "message": "Could not read image file"}
        create_backup(path)
        for values in reversed(history):
            img = _unadjust_image(img, **values)
        _imwrite_image(path, img)
        _forget_adjustments(path)
        _plain_forget(path)
        logging.info(f"Remove All: undid {len(history)} adjustment(s) on {os.path.basename(path)}")
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        return {"status": "success", "message": "Colour adjustments removed", "new_url": new_url}
    except Exception as e:
        logging.error(f"adjust-image-reset failed: {e}")
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
def rotate_image_fine(data: dict = Body(...)):
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

        _imwrite_image(path, rotated_img)
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"

        _geometry_changed(path)
        return {"status": "success", "message": f"Image rotated {angle} degrees", "new_url": new_url}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/deskew-image")
def deskew_image(data: dict = Body(...)):
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
            _imwrite_image(path, rotated_img)
        else:
            # Save rotated image to a temporary path and then re-crop it
            temp_rotated_path = os.path.join(TEMP_DIR, f"rotated_{os.path.basename(path)}")
            _imwrite_image(temp_rotated_path, rotated_img)

            # Now, auto-crop this rotated image to remove the excess borders, overwriting the original file
            auto_crop_image(image_path=temp_rotated_path, output_path=path, padding=int(padding))
            os.remove(temp_rotated_path)

        _geometry_changed(path)
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        return {"status": "success", "message": "Image deskewed", "new_url": new_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Tilt: ABSOLUTE and immediate ------------------------------------------
# Clicking < / > / << / >> sets a single angle measured from the untouched scan
# (1 deg, 2 deg, 3 deg ...) instead of stacking another relative rotation on an
# already-rotated file. A "tilt base" copy of the pixels is kept per file, so
# repeated clicks never compound JPEG loss or drift off the original.
_TILT_STATE = {}          # abspath -> {"written_mtime": float, "angle": float}
_TILT_LOCK = threading.Lock()   # one tilt at a time: never two writers on one file


def _tilt_base_path(image_path):
    safe = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.abspath(image_path))
    return os.path.join(TEMP_DIR, f"{safe}.tiltbase")


def _tilt_base_is_current(image_path):
    """True while our base still matches what we last wrote to the file."""
    state = _TILT_STATE.get(os.path.abspath(image_path))
    if not state or not os.path.exists(_tilt_base_path(image_path)):
        return False
    try:
        return abs(os.path.getmtime(image_path) - state["written_mtime"]) < 1e-6
    except OSError:
        return False


def _replace_file_atomically(source_path, dest_path):
    """Swap a finished file into place in one step.

    The browser re-fetches the image after every tilt, so a half-written file
    must never be visible: readers see either the old picture or the new one.
    """
    temp_path = f"{dest_path}.{time.time_ns()}.tmp"
    try:
        shutil.copy2(source_path, temp_path)
        os.replace(temp_path, dest_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _disc_crop(img, padding=5):
    """Square crop around the disc, so the padding is identical at every angle.

    The disc is found by fitting a circle to everything that differs from the
    background, which is reliable here because the rotation always adds a
    background margin. Returns (crop, (x, y, side)) or (None, None).
    """
    h, w = img.shape[:2]
    border = np.concatenate([img[0, :].reshape(-1, 3), img[-1, :].reshape(-1, 3),
                             img[:, 0].reshape(-1, 3), img[:, -1].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    diff = np.abs(img.astype(np.int16) - bg.astype(np.int16)).max(axis=2)
    mask = (diff > 16).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None
    (cx, cy), radius = cv2.minEnclosingCircle(max(contours, key=cv2.contourArea))
    if radius < 0.15 * min(h, w) or radius > 1.1 * max(h, w):
        return None, None
    side = int(2 * radius + 2 * padding)
    if side < 0.25 * min(h, w) or side > max(h, w):
        return None, None
    x0 = int(round(cx - side / 2.0))
    y0 = int(round(cy - side / 2.0))
    x0 = max(0, min(w - side, x0))
    y0 = max(0, min(h - side, y0))
    return img[y0:y0 + side, x0:x0 + side], (x0, y0, side)


def _rotate_file_by(src_path, dst_path, angle, padding=5, media_type="auto", crop_rect=None):
    """Rotate `src_path` by `angle` degrees, re-crop it, and write over `dst_path`.

    Reads the untouched base and writes the destination, so there is never an
    intermediate copy of the scan on disk.

    The rotated picture gets a small background margin and is then cropped from
    itself - never from the original bed scan - so the padding is correct after
    every rotation. Discs (tape/cd) use a circle fit so the square crop is the
    same at every angle; other artwork goes through the normal auto-crop.

    `crop_rect` (x, y, w, h) replays a crop that was measured earlier, which is
    what makes "Remove All" put the tilt back with exactly the same framing.
    Returns the crop rectangle used, when one can be measured.
    """
    img = cv2.imread(src_path)
    if img is None:
        raise ValueError("Could not read image file")
    (h, w) = img.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, float(angle), 1.0)
    cos, sin = np.abs(M[0, 0]), np.abs(M[0, 1])
    newW, newH = int((h * sin) + (w * cos)), int((h * cos) + (w * sin))
    M[0, 2] += (newW / 2) - center[0]
    M[1, 2] += (newH / 2) - center[1]
    bg = get_image_background_color(img)
    rotated = cv2.warpAffine(img, M, (newW, newH), borderValue=bg)

    # A background margin, so the object never touches the edge and can be found.
    pad_x = max(4, int(newW * 0.04))
    pad_y = max(4, int(newH * 0.04))
    rotated = cv2.copyMakeBorder(rotated, pad_y, pad_y, pad_x, pad_x,
                                 cv2.BORDER_CONSTANT, value=bg)

    used_rect = None
    cropped = None
    if media_type in ("tape", "cd"):
        if crop_rect:
            x0, y0, side = int(crop_rect[0]), int(crop_rect[1]), int(crop_rect[2])
            x0 = max(0, min(rotated.shape[1] - side, x0))
            y0 = max(0, min(rotated.shape[0] - side, y0))
            cropped = rotated[y0:y0 + side, x0:x0 + side]
            used_rect = (x0, y0, side)
        else:
            cropped, used_rect = _disc_crop(rotated, padding=int(padding))

    staged_path = f"{dst_path}.{time.time_ns()}.rot.jpg"
    cropped_path = f"{dst_path}.{time.time_ns()}.crop.jpg"
    try:
        if cropped is not None:
            _imwrite_image(staged_path, cropped)
            os.replace(staged_path, dst_path)
        else:
            # No disc found (or rectangular artwork): let the normal auto-crop
            # work on the rotated picture itself.
            _imwrite_image(staged_path, rotated)
            auto_crop_image(staged_path, output_path=cropped_path,
                            padding=int(padding), media_type=media_type)
            os.replace(cropped_path, dst_path)
    finally:
        for leftover in (staged_path, cropped_path):
            if os.path.exists(leftover):
                try:
                    os.remove(leftover)
                except OSError:
                    pass
    return used_rect


@app.post("/tilt-image")
def tilt_image(data: dict = Body(...)):
    """Set the absolute tilt of a file, always starting from the tilting base."""
    path = data.get("path")
    angle = float(data.get("angle") or 0.0)
    padding = data.get("padding", 5)
    skip_crop = data.get("skip_crop", False)
    media_type = data.get("media_type", "auto")

    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    key = os.path.abspath(path)
    base = _tilt_base_path(path)

    try:
        # Serialised: the page can send follow-up requests in quick succession,
        # and two writers on one file is what corrupted the heap.
        with _TILT_LOCK:
            if abs(angle) < 0.05:
                # Back to zero: put the base back and forget the session.
                if _tilt_base_is_current(path):
                    _replace_file_atomically(base, path)
                    os.remove(base)
                    _TILT_STATE.pop(key, None)
            else:
                if not _tilt_base_is_current(path):
                    # First click, or something else edited the file since the
                    # last tilt - freeze what is on disk now, and keep one
                    # backup so a single Undo returns the pre-tilt scan.
                    create_backup(path)
                    shutil.copy2(path, base)
                    _TILT_STATE[key] = {"written_mtime": os.path.getmtime(path), "angle": 0.0}
                rect = _rotate_file_by(base, path, angle, padding=padding, media_type=media_type)
                _TILT_STATE[key]["written_mtime"] = os.path.getmtime(path)
                _TILT_STATE[key]["angle"] = angle
                _TILT_STATE[key]["media_type"] = media_type
                _TILT_STATE[key]["crop_rect"] = rect

        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        logging.info(f"Tilt: {os.path.basename(path)} set to {angle:+.1f} deg")
        return {"status": "success", "angle": angle, "new_url": new_url}
    except Exception as e:
        logging.error(f"tilt-image failed: {e}")
        return {"status": "error", "message": str(e)}


# --- CD/45 Front: make the printed text level --------------------------------
# Levelling only, and all of it local: no network call, so the result is the same
# every time and a scan can never be left quarter-turned by a guess. Rotate
# candidate angles and keep the one whose text rows line up best - word-blob
# consensus first (works at any label angle), narrow projection sweep as the
# fallback. When the evidence is ambiguous the scan is left exactly as scanned.
def _front_small(gray, max_side=800):
    """Downscale for the orientation/skew maths - details do not matter there."""
    h, w = gray.shape[:2]
    scale = min(1.0, float(max_side) / float(max(h, w) or 1))
    if scale < 1.0:
        gray = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    return gray


def _text_line_score(gray):
    """High score => ink is organised in horizontal text rows. None if not text."""
    if gray is None or gray.size == 0:
        return None
    _, binimg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = float(binimg.mean()) / 255.0
    if ink < 0.01 or ink > 0.55:            # blank page or a photo, not text
        return None
    rows = binimg.sum(axis=1, dtype=np.float64)
    if rows.mean() <= 0:
        return None
    return float(rows.var() / (rows.mean() ** 2))


def _rotate_with_background(img, angle):
    """Rotate by `angle` degrees (OpenCV convention: positive = counter-clockwise),
    filling the corners with the image's own background colour."""
    (h, w) = img.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += new_w / 2.0 - center[0]
    M[1, 2] += new_h / 2.0 - center[1]
    return cv2.warpAffine(img, M, (new_w, new_h), borderValue=get_image_background_color(img))


def _word_like_blobs(gray):
    """Word-sized, elongated ink blobs - each one's long axis is its text angle.

    A label line becomes a run of word blobs that all share an angle, which is
    what makes this rotation-invariant: no sweep is needed, so a disc label at
    33 deg is measured as easily as one at 3 deg.
    """
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binimg = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = float(binimg.mean()) / 255.0
    if not (0.005 <= ink <= 0.55):        # blank page, or a photo, not text
        return []
    binimg = cv2.morphologyEx(binimg, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    contours, _ = cv2.findContours(binimg, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    area = float(h * w)
    blobs = []
    for c in contours:
        if not (40 <= cv2.contourArea(c) <= 0.02 * area):
            continue
        (cx, cy), (rw, rh), deg = cv2.minAreaRect(c)
        long_side, short_side = max(rw, rh), max(1.0, min(rw, rh))
        if long_side < 20 or long_side / short_side < 2.2:
            continue
        # A word is mostly gaps between glyphs (fill ~0.5); a solid shape - a
        # printed block, a photo highlight - fills its rectangle. Without this
        # an abstract cover can "agree" on an angle and get rotated for nothing.
        if not (0.12 <= cv2.contourArea(c) / max(1.0, rw * rh) <= 0.70):
            continue
        box = cv2.boxPoints(((cx, cy), (rw, rh), deg))
        edges = [(np.linalg.norm(box[(i + 1) % 4] - box[i]), box[(i + 1) % 4] - box[i])
                 for i in range(4)]
        v = max(edges, key=lambda t: t[0])[1]
        angle = float(np.degrees(np.arctan2(v[1], v[0]))) % 180.0
        if angle > 90:
            angle -= 180.0
        blobs.append({"angle": angle, "contour": c})
    return blobs


def _text_axis_consensus(blobs, tolerance=3.0):
    """The angle most word blobs agree on, or None if there is no majority.

    Radial/curved label text points every which way, and photo texture produces
    scattered blobs, so both fail the majority test and are left alone.
    """
    if len(blobs) < 4:
        return None
    angles = np.array([b["angle"] for b in blobs])
    best = None
    for probe in angles:
        delta = np.abs((angles - probe + 90.0) % 180.0 - 90.0)
        members = np.nonzero(delta <= tolerance)[0]
        fraction = len(members) / len(angles)
        if best is None or (len(members), fraction) > (best["count"], best["fraction"]):
            best = {"count": len(members), "fraction": fraction,
                    "median": float(np.median(angles[members])), "members": members}
    if best is None or best["fraction"] < 0.6:
        return None
    return best


def _mask_row_sharpness(mask, angle):
    """How sharply the mask's ink collapses into rows when rotated by `angle`."""
    pad = 60
    padded = cv2.copyMakeBorder(mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    h, w = padded.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), float(angle), 1.0)
    rotated = cv2.warpAffine(padded, M, (w, h), borderValue=0)
    return float(rotated.sum(axis=1, dtype=np.float64).var())


def _detect_skew_from_words(gray):
    """Angle (OpenCV convention) that levels the text, found from word blobs.

    Returns None when the evidence is not convincing, so the caller can fall
    back to the narrow projection sweep.
    """
    blobs = _word_like_blobs(gray)
    consensus = _text_axis_consensus(blobs)
    if consensus is None:
        return None
    if consensus["count"] < 3:
        return None

    # Refine on the agreeing blobs only: artwork and label screens cannot drag
    # the angle, which is what made a whole-image sweep unreliable at wide angles.
    mask = np.zeros(gray.shape[:2], np.uint8)
    for i in consensus["members"]:
        cv2.drawContours(mask, [blobs[i]["contour"]], -1, 255, -1)
    coarse = consensus["median"]
    candidates = [coarse + i * 0.25 for i in range(-8, 9)]      # +-2 deg
    return max(candidates, key=lambda a: _mask_row_sharpness(mask, a))


def _detect_skew_from_projection(gray, search=10.0):
    """Narrow row-projection sweep - the original method, kept as a fallback."""
    def best_over(angles):
        best_angle, best_score = 0.0, None
        for a in angles:
            probe = _rotate_with_background(gray, a) if a else gray
            score = _text_line_score(probe)
            if score is not None and (best_score is None or score > best_score):
                best_angle, best_score = a, score
        return best_angle, best_score

    # 1 deg sweep, then 0.25 deg around the winner.
    coarse, coarse_score = best_over([i * 1.0 for i in range(int(-search), int(search) + 1)])
    if coarse_score is None:
        return 0.0                        # nothing text-like to level
    fine, fine_score = best_over([coarse + i * 0.25 for i in range(-4, 5)])
    if fine_score is None:
        fine, fine_score = coarse, coarse_score

    # A winner pressed against the end of the search range means the score is
    # being driven by the artwork's geometry, not by text rows - refuse it.
    if abs(fine) >= search - 0.5:
        logging.info(f"CD/45 Front: skew hit the search edge ({fine:.1f} deg) - ignoring it.")
        return 0.0

    # Only straighten when the winning angle beats "leave it as is" clearly.
    upright_score = _text_line_score(gray)
    if upright_score is None or fine_score < upright_score * 1.10:
        return 0.0

    # Ignore sub-half-degree noise - a tiny warp still costs a JPEG re-encode.
    return 0.0 if abs(fine) < 0.5 else fine


def _detect_text_skew(img):
    """Angle (OpenCV convention) that levels the text; 0.0 when unsure.

    Word-blob consensus first (works at any label angle), narrow projection
    sweep as the fallback. Without an orientation pass a line of text cannot be
    told from the same line upside down, so only a modest lean is corrected -
    a large angle is just as likely to be the perpendicular reading, and
    leaving the scan alone beats guessing.
    """
    gray = _front_small(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), max_side=1400)
    limit = 15.0

    # Word blobs need enough pixels per letter: a full bed at 800px has none,
    # so measure at the larger size too. If the two disagree the geometry is
    # ambiguous, and leaving the scan alone beats guessing.
    answers = {}
    for max_side in (1400, 800):
        probe = _front_small(gray, max_side) if max(gray.shape[:2]) > max_side else gray
        found = _detect_skew_from_words(probe)
        if found is not None:
            answers[max_side] = found
    if len(answers) == 2 and abs(answers[1400] - answers[800]) > 3.0:
        logging.info(f"CD/45 Front: word angles disagree ({answers[1400]:.1f} vs "
                     f"{answers[800]:.1f} deg) - leaving as is.")
        return 0.0
    angle = answers.get(1400, answers.get(800))

    if angle is not None:
        if abs(angle) > limit:
            logging.info(f"CD/45 Front: word angle {angle:.1f} deg is ambiguous - leaving as is.")
            return 0.0
        return 0.0 if abs(angle) < 0.5 else angle

    return _detect_skew_from_projection(_front_small(gray, 800))


def straighten_front_image(path, padding=5):
    """Level a CD/45 front scan so its printed text sits straight.

    Purely local - no AI call, so the outcome is repeatable and a scan can never
    be left quarter-turned by a guess. Returns (bool, message). Backs the file up
    first, like every other edit, so Undo still works. Never raises: a failure
    here must not break the scan.
    """
    if not path or not os.path.exists(path):
        return False, "File not found"
    try:
        img = cv2.imread(path)
        if img is None:
            return False, "Could not read image"
        logging.info(f"CD/45 Front: levelling {os.path.basename(path)} ({img.shape[1]}x{img.shape[0]})")

        try:
            skew = _detect_text_skew(img)
        except Exception as e:
            logging.warning(f"CD/45 Front: levelling step failed ({e}) - continuing without it")
            skew = 0.0

        if abs(skew) < 0.5:
            logging.info("CD/45 Front: text already level.")
            return True, "Already level."

        create_backup(path)
        _imwrite_image(path, _rotate_with_background(img, skew))
        message = f"Levelled {abs(skew):.1f}deg"
        logging.info(f"CD/45 Front: {message} (total {skew:.2f})")
        return True, message
    except Exception as e:
        logging.error(f"CD/45 Front straighten failed: {e}")
        return False, str(e)


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
        _imwrite_image(path, rotated_img)
        
        return True, f"Auto-aligned ({angle:.2f}°)"

    except Exception as e:
        logging.error(f"Auto-deskew error: {e}")
        return False, str(e)

@app.post("/auto-deskew")
def auto_deskew(data: dict = Body(...)):
    path = data.get("path")
    padding = data.get("padding", 5)
    if not path or not os.path.exists(path):
        return {"status": "error", "message": "File not found"}

    success, message = perform_auto_deskew(path, padding)
    
    _geometry_changed(path)
    if success or message == "Already aligned.":
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        return {"status": "success", "message": message, "new_url": new_url}
    else:
        return {"status": "error", "message": message}

@app.post("/manual-crop")
def manual_crop(data: dict = Body(...)):
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
        _geometry_changed(path)
        _imwrite_image(path, cropped_img) # Overwrite the existing file
        return {"status": "success", "message": "Image cropped successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/manual-crop-as-new")
def manual_crop_as_new(data: dict = Body(...)):
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
        _imwrite_image(new_filepath, cropped_img)

        return { "status": "success", "message": "New cropped image created.", "cropped_path": new_filepath, "cropped_url": f"/view-image?path={urllib.parse.quote(new_filepath)}" }
    except Exception as e: 
        return {"status": "error", "message": str(e)}

@app.post("/manual-crop-replace")
def manual_crop_replace(data: dict = Body(...)):
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
        _geometry_changed(target_path)
        _imwrite_image(target_path, cropped_img)

        return {"status": "success", "message": "Image cropped and replaced successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/detect-bounds")
def detect_bounds(data: dict = Body(...)):
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
def revert_crop(data: dict = Body(...)):
    original_path = data.get("original_path")
    cropped_path = data.get("cropped_path")

    if not original_path or not os.path.exists(original_path):
        return {"status": "error", "message": "Original file not found."}
    
    if not cropped_path:
        return {"status": "error", "message": "Target path not specified."}

    try:
        create_backup(cropped_path)
        shutil.copy(original_path, cropped_path)
        _plain_forget(cropped_path)
        _forget_adjustments(cropped_path)
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
def cleanup_backups():
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
def manage_files(data: dict = Body(...)):
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

                _imwrite_image(dest_path, img)

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
                    _forget_adjustments(file_path)
                    _plain_forget(file_path)
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
def open_folder(data: dict = Body(default={})):
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
def open_file(data: dict = Body(...)):
    path = data.get("path", "")
    
    if "view-image?path=" in path:
        path = path.split("view-image?path=")[-1].split("&")[0]
    path = urllib.parse.unquote(path)
    
    if not path or not _is_image_file(path) or not _is_under_allowed_root(path):
        return {"status": "error", "message": "File not allowed"}
    try:
        # Use os.path.abspath to ensure startfile works correctly
        os.startfile(os.path.abspath(path))
        return {"status": "success", "message": f"Opened file: {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/get-groups")
def get_groups(path: str = None):
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
def get_group_images(group_name: str, path: str = None):
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

@app.post("/undo-action")
def undo_action(data: dict = Body(...)):
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
        _plain_forget(path)
        logging.info(f"Restored {path} from {primary_backup_path}")
        _forget_adjustments(path)      # restored pixels: the colour history is stale

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
        
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        
        return {"status": "success", "message": "Last action undone.", "new_url": new_url}
    except Exception as e:
        logging.error(f"Undo failed for {path}: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/redo-action")
def redo_action(data: dict = Body(...)):
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
        _plain_forget(path)
        _forget_adjustments(path)      # restored pixels: the colour history is stale
        
        new_url = f"/view-image?path={urllib.parse.quote(path)}&v={time.time_ns()}"
        return {"status": "success", "message": "Redo successful.", "new_url": new_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}

LAST_HEARTBEAT = time.time()
PAGE_HIDDEN = False

@app.post("/api/heartbeat")
async def heartbeat(request: Request):
    global LAST_HEARTBEAT, PAGE_HIDDEN
    LAST_HEARTBEAT = time.time()
    try:
        data = await request.json()
        PAGE_HIDDEN = bool(data.get("hidden")) if isinstance(data, dict) else False
    except Exception:
        PAGE_HIDDEN = False
    return {"status": "ok"}


# --- Native "always on top" pin ---------------------------------------------
# The Extract Text panel lives in its own browser window, and a web page cannot
# make its own OS window stay above other applications. So the pin button asks
# this server to do it: find the window by its caption (the page title) and flip
# SetWindowPos(HWND_TOPMOST). Same contract as the WYSIWYG app's /api/window-pin,
# duplicated here because the scanner can also be built/run standalone.
_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010

_USER32 = None


def _user32():
    """user32 with explicit argtypes so 64-bit HWND values survive the call."""
    import ctypes
    from ctypes import wintypes
    global _USER32
    if _USER32 is None:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsWindowVisible.restype = wintypes.BOOL
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u.SetWindowPos.restype = wintypes.BOOL
        _USER32 = u
    return _USER32


def _win_pseudo_hwnd(value):
    """HWND_TOPMOST/-NOTOPMOST arrive as -1/-2; ctypes needs the unsigned form."""
    import ctypes
    return ctypes.c_void_p(value & (2 ** (8 * ctypes.sizeof(ctypes.c_void_p)) - 1))


def _win_find_by_title(title):
    """Visible top-level window whose caption is `title` (or starts with it, so a
    Chrome suffix such as ' - Google Chrome' still matches)."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    exact, prefix = [], []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            caption = buf.value
            if caption == title:
                exact.append(hwnd)
            elif caption.startswith(title):
                prefix.append(hwnd)
        return True

    user32.EnumWindows(_enum_proc, 0)
    candidates = exact or prefix
    if not candidates:
        return None
    foreground = user32.GetForegroundWindow()
    return foreground if foreground in candidates else candidates[0]


def _win_is_topmost(hwnd):
    return bool(_user32().GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOPMOST)


def _win_set_topmost(hwnd, on):
    import ctypes
    ok = _user32().SetWindowPos(hwnd, _win_pseudo_hwnd(-1 if on else -2), 0, 0, 0, 0,
                                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


@app.get("/api/window-pin")
async def window_pin_state(title: str = ""):
    """Reports whether the window with this caption is currently always-on-top."""
    if os.name != "nt":
        return JSONResponse(status_code=501, content={"status": "error", "message": "Windows only."})
    title = (title or "").strip()
    if not title:
        return JSONResponse(status_code=400, content={"status": "error", "message": "title is required."})
    hwnd = _win_find_by_title(title)
    if not hwnd:
        return {"status": "success", "found": False, "topmost": None}
    return {"status": "success", "found": True, "topmost": _win_is_topmost(hwnd)}


@app.post("/api/window-pin")
async def window_pin_set(data: dict = Body(...)):
    """Turns always-on-top on/off for the window with the given caption."""
    if os.name != "nt":
        return JSONResponse(status_code=501, content={"status": "error", "message": "Windows only."})
    title = (data.get("title") or "").strip()
    if not title:
        return JSONResponse(status_code=400, content={"status": "error", "message": "title is required."})
    hwnd = _win_find_by_title(title)
    if not hwnd:
        return {"status": "error", "message": f"Window not found: {title}"}
    try:
        _win_set_topmost(hwnd, bool(data.get("topmost")))
    except Exception as e:
        return {"status": "error", "message": str(e)}
    return {"status": "success", "found": True, "topmost": _win_is_topmost(hwnd)}

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
        global LAST_HEARTBEAT, PAGE_HIDDEN
        # Allow 15 seconds for browser to load and send initial heartbeat
        time.sleep(15)
        while True:
            time.sleep(2)
            if PAGE_HIDDEN:
                # Chrome throttles timers in background tabs (down to ~1/min),
                # so only give up on a hidden page after a long grace period.
                limit = 1800
            else:
                limit = 120
            if time.time() - LAST_HEARTBEAT > limit:
                logging.info(f"No heartbeat received for {limit} seconds. Shutting down WysiScan server...")
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
    # Dialog-runner mode ("-c <code>") used by the bundled Image Convert app.
    if "-c" in sys.argv:
        try:
            code_to_run = sys.argv[sys.argv.index("-c") + 1]
            exec(code_to_run)
            sys.exit(0)
        except Exception:
            logging.exception("Failed to execute dynamic code via -c")
            sys.exit(1)

    # Image Convert sub-app (GUI or --source/--output batch mode).
    if "--imageconvert" in sys.argv:
        sys.argv.remove("--imageconvert")
        if hasattr(sys, "_MEIPASS") and sys._MEIPASS not in sys.path:
            sys.path.insert(0, sys._MEIPASS)
        try:
            from imageconvert.app import main as run_imageconvert
        except ImportError:
            from WysiScan.imageconvert.app import main as run_imageconvert
        run_imageconvert()
        sys.exit(0)

    # Dialog-runner mode (used by the frozen standalone exe for Browse dialogs):
    # run a script with stdout redirected to a result file, then exit.
    if "--run-script" in sys.argv:
        import runpy
        script_path = sys.argv[sys.argv.index("--run-script") + 1]
        result_path = sys.argv[sys.argv.index("--run-result") + 1]
        with open(result_path, "w", encoding="utf-8") as fh:
            previous_stdout = sys.stdout
            sys.stdout = fh
            try:
                runpy.run_path(script_path, run_name="__main__")
            finally:
                sys.stdout = previous_stdout
        sys.exit(0)
    run_server()