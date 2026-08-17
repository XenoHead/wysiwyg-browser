import os
import sys
import shutil
import tempfile
import subprocess
import threading
import traceback
import webview
from PIL import Image, ImageOps

# Ensure current directory is in Python path for local loads
if getattr(sys, 'frozen', False):
    # In frozen mode, when imported or run, __file__ points to the file inside sys._MEIPASS
    if '__file__' in globals():
        current_dir = os.path.dirname(os.path.abspath(__file__))
    else:
        current_dir = os.path.join(sys._MEIPASS, "WysiScan", "imageconvert")
    app_base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_base_dir = current_dir

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


def run_dialog_script(script):
    """
    Runs a tkinter dialog script in a separate python process to avoid 
    GUI loop conflicts/deadlocks with Webview2.
    """
    import tempfile
    fd, temp_path = tempfile.mkstemp(suffix='.txt')
    os.close(fd)
    
    safe_script = f"""
import sys
def print(*args, **kwargs):
    with open(r'''{temp_path}''', 'w', encoding='utf-8') as _temp_f:
        _temp_f.write(" ".join(str(a) for a in args))
""" + script

    python_exe = sys.executable
    if python_exe.endswith('pythonw.exe'):
        python_exe = python_exe.replace('pythonw.exe', 'python.exe')
    cmd = [python_exe, '-c', safe_script]
        
    creationflags = 0
    if os.name == 'nt':
        creationflags = 0x08000000  # CREATE_NO_WINDOW
        
    try:
        subprocess.check_call(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        with open(temp_path, 'r', encoding='utf-8') as f:
            result = f.read().strip()
        os.remove(temp_path)
        return result if result and result != "None" and result != "" else None
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except: pass
        return None


class ImageConverterAPI:
    def __init__(self):
        self._active_window = None
        self._load_config()

    def _load_config(self):
        import json
        self.config_path = os.path.join(app_base_dir, 'config.json')
        self.last_opened_dir = os.path.expanduser("~")
        self.last_output_dir = ""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.last_opened_dir = data.get('last_opened_dir', self.last_opened_dir)
                    self.last_output_dir = data.get('last_output_dir', '')
            except Exception as e:
                print(f"Error loading config: {e}")

    def _save_config(self):
        import json
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'last_opened_dir': self.last_opened_dir,
                    'last_output_dir': self.last_output_dir
                }, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_saved_folders(self):
        return {
            "last_opened_dir": self.last_opened_dir,
            "last_output_dir": self.last_output_dir
        }

    def select_folder_dialog(self, title="Select Image Directory"):
        script = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
folder = filedialog.askdirectory(parent=root, title="{title}", initialdir=r"{self.last_opened_dir}")
print(folder)
"""
        res = run_dialog_script(script)
        if res and os.path.exists(res):
            self.last_opened_dir = res
            self._save_config()
            return {"status": "success", "path": res, "files": self._scan_for_images(res)}
        return {"status": "cancelled"}

    def select_files_dialog(self, title="Select Image Files"):
        filetypes = "[('Image Files', '*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tiff;*.gif'), ('All Files', '*.*')]"
        script = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
files = filedialog.askopenfilenames(parent=root, title="{title}", initialdir=r"{self.last_opened_dir}", filetypes={filetypes})
if files:
    print(";".join(files))
"""
        res = run_dialog_script(script)
        if res:
            files_list = res.split(";")
            if files_list:
                self.last_opened_dir = os.path.dirname(os.path.abspath(files_list[0]))
                self._save_config()
                details = []
                for f in files_list:
                    if os.path.exists(f):
                        sz = os.path.getsize(f)
                        details.append({
                            "path": f,
                            "name": os.path.basename(f),
                            "size": self._format_bytes(sz)
                        })
                return {"status": "success", "files": details}
        return {"status": "cancelled"}

    def select_output_folder_dialog(self, title="Select Output Folder"):
        script = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
folder = filedialog.askdirectory(parent=root, title="{title}", initialdir=r"{self.last_opened_dir}")
print(folder)
"""
        res = run_dialog_script(script)
        if res and os.path.exists(res):
            self.last_output_dir = res
            self._save_config()
            return res
        return None

    def _scan_for_images(self, folder_path):
        valid_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.gif'}
        images = []
        try:
            # Only scan the root of the selected folder (no subfolders).
            for f in os.listdir(folder_path):
                full_path = os.path.join(folder_path, f)
                if not os.path.isfile(full_path):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    sz = os.path.getsize(full_path)
                    images.append({
                        "path": full_path,
                        "name": f,
                        "size": self._format_bytes(sz)
                    })
        except Exception as e:
            print(f"Error scanning: {e}")
        return images

    def _format_bytes(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def start_batch_conversion(self, file_paths, output_folder, format_type, width, height, scale_mode, quality, bg_color):
        """Spawns background thread for the image conversion to prevent UI freezes"""
        threading.Thread(
            target=self._run_conversion_thread,
            args=(file_paths, output_folder, format_type, int(width), int(height), scale_mode, int(quality), bg_color),
            daemon=True
        ).start()
        return True

    def _run_conversion_thread(self, file_paths, output_folder, format_type, w, h, scale_mode, quality, bg_color_hex):
        total = len(file_paths)
        if total == 0:
            self._log_js("No files to convert.", "error")
            return

        os.makedirs(output_folder, exist_ok=True)
        self._log_js(f"Starting batch conversion of {total} images to {format_type.upper()} ({w}x{h})...", "info")

        success_count = 0
        fail_count = 0

        # Parse background color hex to tuple
        bg_color = (0, 0, 0, 0)
        if bg_color_hex:
            try:
                hex_str = bg_color_hex.lstrip('#')
                if len(hex_str) == 6:
                    bg_color = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
                elif len(hex_str) == 8:
                    bg_color = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4, 6))
            except:
                bg_color = (0, 0, 0, 0)

        for i, file_path in enumerate(file_paths):
            name = os.path.basename(file_path)
            try:
                self._update_progress_js(i, total, f"Converting {name}...", "info")
                
                # Load image
                with Image.open(file_path) as img:
                    orig_w, orig_h = img.size
                    
                    # Target dimension calculation & resizing
                    resized_img = None
                    
                    if scale_mode == "stretch":
                        resized_img = img.resize((w, h), Image.Resampling.LANCZOS)
                        
                    elif scale_mode == "crop":
                        # Crop to fill the container completely
                        resized_img = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
                        
                    elif scale_mode == "fit":
                        # Proportional fit inside dimension bounds with background filling if needed
                        img.thumbnail((w, h), Image.Resampling.LANCZOS)
                        
                        # Determine if target format supports transparency
                        has_alpha = (format_type.lower() == 'png' or format_type.lower() == 'webp')
                        mode = 'RGBA' if has_alpha else 'RGB'
                        
                        # If image mode is RGBA but output doesn't support alpha, flatten it
                        if img.mode == 'RGBA' and not has_alpha:
                            # Flatten alpha on background color
                            bg = Image.new('RGB', img.size, bg_color[:3])
                            bg.paste(img, mask=img.split()[3])
                            img = bg
                        
                        # Create background canvas
                        canvas_bg = bg_color if has_alpha else bg_color[:3]
                        # If canvas_bg has transparency but mode is RGB, default to black/white
                        if mode == 'RGB' and len(canvas_bg) == 4:
                            canvas_bg = canvas_bg[:3]
                            
                        resized_img = Image.new(mode, (w, h), canvas_bg)
                        
                        # Center thumbnail on the canvas
                        offset_x = (w - img.width) // 2
                        offset_y = (h - img.height) // 2
                        resized_img.paste(img, (offset_x, offset_y))
                        
                    else:  # "proportional" (or "scale")
                        # Scale image proportionally so the longest edge fits the target dimensions without cropping or border padding.
                        aspect = orig_w / orig_h
                        if orig_w > orig_h:
                            new_w = w
                            new_h = max(1, int(w / aspect))
                        else:
                            new_h = h
                            new_w = max(1, int(h * aspect))
                        
                        resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    # Determine output name & path
                    base_name, _ = os.path.splitext(name)
                    ext = f".{format_type.lower()}"
                    
                    # Prevent overwriting source if output folder is same as input folder
                    out_filename = base_name + ext
                    out_path = os.path.join(output_folder, out_filename)
                    
                    # Convert color modes before saving if target format requires it
                    save_img = resized_img
                    if format_type.lower() in ('jpg', 'jpeg'):
                        if save_img.mode in ('RGBA', 'LA'):
                            # Flatten transparent PNG to RGB with custom background fill
                            background = Image.new("RGB", save_img.size, bg_color[:3])
                            background.paste(save_img, mask=save_img.split()[3] if save_img.mode == 'RGBA' else save_img.split()[1])
                            save_img = background
                        elif save_img.mode != 'RGB':
                            save_img = save_img.convert('RGB')
                    else:
                        # For PNG/WEBP, keep mode or convert appropriately
                        if save_img.mode not in ('RGB', 'RGBA', 'L', 'LA'):
                            save_img = save_img.convert('RGBA')

                    # Save image
                    if format_type.lower() in ('jpg', 'jpeg'):
                        save_img.save(out_path, format="JPEG", quality=quality)
                    elif format_type.lower() == 'png':
                        save_img.save(out_path, format="PNG")
                    elif format_type.lower() == 'webp':
                        save_img.save(out_path, format="WEBP", quality=quality)
                    else:
                        save_img.save(out_path, format=format_type.upper())
                        
                    success_count += 1
                    self._log_js(f"Success: {name} -> {out_filename}", "success")
            
            except Exception as e:
                fail_count += 1
                trace = traceback.format_exc()
                print(trace)
                self._log_js(f"Failed to convert {name}: {str(e)}", "error")

        self._update_progress_js(total, total, "Conversion Finished!", "success")
        self._log_js(f"--- BATCH COMPLETED ---", "success")
        self._log_js(f"Successfully converted: {success_count} files", "success")
        if fail_count > 0:
            self._log_js(f"Failed: {fail_count} files", "error")
            
        # Trigger completed event on front end
        if self._active_window:
            self._active_window.evaluate_js(f"onConversionComplete({success_count}, {fail_count})")

    def _log_js(self, message, status="info"):
        if self._active_window:
            escaped = message.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
            self._active_window.evaluate_js(f"addLogEntry('{escaped}', '{status}')")
        else:
            print(f"[{status.upper()}] {message}")

    def _update_progress_js(self, current, total, message, status="info"):
        if self._active_window:
            escaped = message.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
            self._active_window.evaluate_js(f"updateProgress({current}, {total}, '{escaped}', '{status}')")
        else:
            percent = int((current / total) * 100) if total > 0 else 0
            print(f"[{status.upper()}] Progress: {percent}% ({current}/{total}) - {message}")

    def exit_app(self):
        os._exit(0)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Vivid Image Converter CLI / GUI Utility")
    parser.add_argument('--source', '-s', type=str, help="Source image folder path, or a single image path")
    parser.add_argument('--output', '-o', type=str, help="Output destination folder path (default: same as source)")
    parser.add_argument('--format', '-f', type=str, choices=['jpg', 'png', 'webp'], default='jpg', help="Output format (default: jpg)")
    parser.add_argument('--width', '-w', type=int, default=1920, help="Target width in pixels (default: 1920)")
    parser.add_argument('--height', '-t', type=int, default=1080, help="Target height in pixels (default: 1080)")
    parser.add_argument('--scale', '-m', type=str, choices=['proportional', 'crop', 'fit', 'stretch'], default='proportional', help="Resizing scale mode (default: proportional)")
    parser.add_argument('--quality', '-q', type=int, default=90, help="Quality value 1-100 for lossy formats (default: 90)")
    parser.add_argument('--bg-color', '-c', type=str, default='#000000', help="Canvas background fill color in hex (default: #000000)")

    args = parser.parse_args()

    if args.source:
        # --- CLI Mode ---
        api = ImageConverterAPI()
        
        # Scan files
        if os.path.isdir(args.source):
            files = api._scan_for_images(args.source)
            file_paths = [f['path'] for f in files]
        elif os.path.isfile(args.source):
            file_paths = [args.source]
        else:
            print(f"[ERROR] Source path does not exist: {args.source}")
            sys.exit(1)
            
        if not file_paths:
            print(f"[WARN] No valid images found in source: {args.source}")
            sys.exit(0)
            
        output_dir = args.output
        if not output_dir:
            # Default to source directory or parent directory of file
            if os.path.isdir(args.source):
                output_dir = args.source
            else:
                output_dir = os.path.dirname(os.path.abspath(args.source))
                
        print(f"\n--- Starting CLI Image Conversion ---")
        print(f"Source: {args.source} ({len(file_paths)} files)")
        print(f"Output: {output_dir}")
        print(f"Settings: {args.width}x{args.height}, Format: {args.format.upper()}, Scale Mode: {args.scale}, Quality: {args.quality}%")
        print(f"Background: {args.bg_color}\n")
        
        api._run_conversion_thread(
            file_paths=file_paths,
            output_folder=output_dir,
            format_type=args.format,
            w=args.width,
            h=args.height,
            scale_mode=args.scale,
            quality=args.quality,
            bg_color_hex=args.bg_color
        )
        print("\n--- CLI Conversion Completed ---\n")
        sys.exit(0)
    else:
        # --- GUI Mode ---
        api = ImageConverterAPI()
        html_path = os.path.join(current_dir, 'index.html')
        
        # Create window
        active_window = webview.create_window(
            'Vivid Image Converter',
            url=html_path,
            js_api=api,
            width=1150,
            height=750,
            background_color='#0a0a0c'
        )
        api._active_window = active_window
        
        # Start webview
        webview.start(debug=False)


if __name__ == '__main__':
    main()
