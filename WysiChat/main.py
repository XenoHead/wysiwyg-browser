import sys
import socket
import threading
import sqlite3
import os
import winsound
import shutil
import ctypes
import subprocess
import time
from datetime import datetime
from cryptography.fernet import Fernet
import argparse
from PIL import Image, ImageDraw
import json
import logging
import webbrowser
import re


import FreeSimpleGUI as sg 

# Wrap FreeSimpleGUI popups to always keep on top to prevent window lockups
def wrap_popup(func):
    def wrapper(*args, **kwargs):
        kwargs.setdefault('keep_on_top', True)
        return func(*args, **kwargs)
    return wrapper

sg.popup = wrap_popup(sg.popup)
sg.popup_yes_no = wrap_popup(sg.popup_yes_no)
sg.popup_error = wrap_popup(sg.popup_error)
sg.popup_get_text = wrap_popup(sg.popup_get_text)
sg.popup_scrolled = wrap_popup(sg.popup_scrolled)

# --- ARGUMENTS & SETTINGS SETUP ---
# Moved up so we can use 'args.name' for the settings filename immediately
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=5555, help="Port to listen on")
parser.add_argument("--name", type=str, default=socket.gethostname(), help="Unique machine name")
args, _ = parser.parse_known_args()
PORT = args.port
MY_NAME = args.name
APP_VERSION = "2.0.0"

# --- USER & SETTINGS MANAGEMENT ---
# Determine the actual folder where the app/script is running
if getattr(sys, 'frozen', False):
    script_dir = os.path.dirname(sys.executable) # For .exe
else:
    script_dir = os.path.dirname(os.path.abspath(__file__)) # For .py

# --- LOGGING SETUP ---
log_file = os.path.join(script_dir, "wysichat_debug.log")
logging.basicConfig(
    filename=log_file, 
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w' # Overwrite log on each restart to keep it clean
)

# 1. Load Machine Configuration to see who was last logged in
machine_conf_file = f'machine_conf_{MY_NAME}.json'
sg.user_settings_filename(filename=machine_conf_file, path=script_dir)

my_alias = sg.user_settings_get_entry('-LAST-USER-', None)
if not my_alias:
    my_alias = sg.popup_get_text(f"Enter Chat Alias for {MY_NAME}:")
    if my_alias:
        sg.user_settings_set_entry('-LAST-USER-', my_alias)
    else:
        sys.exit()
my_alias = my_alias.strip() # Ensure no trailing spaces cause DB mismatches

# 2. Switch to User-Specific Settings & Database
sg.user_settings_filename(filename=f'user_prefs_{my_alias}.json', path=script_dir)
DB_FILE = os.path.join(script_dir, f"chat_history_{my_alias}.db")
logging.info(f"Session Started. User: {my_alias} | DB: {DB_FILE}")

# --- CONFIGURATION & SECURITY ---
# Hard-code a key here so all instances can decrypt each other's messages
# To generate a new one: Fernet.generate_key()
SECRET_KEY = b'enetZvIzFVUY6MR8cQKEig3qGpYdh4_7_OHNDsr02lo='
cipher = Fernet(SECRET_KEY)

# Fix Taskbar Icon: Tells Windows this is a distinct app, not just "Python"
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('WysiChat.App.2.0')
except AttributeError:
    pass

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# --- RESOLVE FYRTOOLS ROOT ---
def resolve_fyrtools_root():
    r"""
    Scans the local storage layout and network topology to map the active root path.
    Prioritizes the physical host drive 'C:\FYRShare' to minimize loopback and permission 
    latency when running locally on the GREENLANTERN central node.
    """
    possible_roots = [
        r"C:\FYRShare\Tools\FYRTools",                       # Central host local drive mapping (Prioritized)
        r"Z:\Tools\FYRTools",                                 # Standard client network drive shortcut (Store/Warehouse)
        r"\\192.168.0.108\FYRShare\Tools\FYRTools"            # Universal UNC network share path fallback
    ]
    for root in possible_roots:
        if os.path.exists(root):
            return root
    # Dynamic runtime fallback if the drive letter or network path is temporarily inaccessible
    return r"Z:\Tools\FYRTools"

FYRTOOLS_ROOT = resolve_fyrtools_root()
# Standardized base path for Wysichat network assets
SHARED_PATH = os.path.join(FYRTOOLS_ROOT, "WysiChat")


# --- SETTINGS & PERSISTENCE ---
# Settings filename is now set at the top of the script
sent_col = sg.user_settings_get_entry('-SENT-COLOR-', 'blue')
recv_col = sg.user_settings_get_entry('-RECV-COLOR-', 'dark green')
f_family = sg.user_settings_get_entry('-FONT-FAMILY-', 'Segoe UI')
f_size = sg.user_settings_get_entry('-FONT-SIZE-', 12)

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # Check if table exists
    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='messages'")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, sender TEXT, recipient TEXT, message TEXT, direction TEXT
            )
        """)
    else:
        # Check for missing columns (migration for older DBs)
        cur.execute("PRAGMA table_info(messages)")
        cols = [info[1] for info in cur.fetchall()]
        if 'recipient' not in cols:
            print("Migrating DB: Adding 'recipient' column...")
            cur.execute("ALTER TABLE messages ADD COLUMN recipient TEXT")
    conn.commit()
    conn.close()

# --- PRESENCE PROTOCOL (ANNOUNCE SELF) ---
def announce_self(alias, status="Online"):
    """
    Registers client availability metadata on the shared network layout.
    Differentiates host configurations by name (GREENLANTERN) or local drive profile
    to circumvent Windows Loopback connection restrictions, enforcing the correct host IP.
    """
    contact_path = os.path.join(SHARED_PATH, "Contacts")
    try:
        if not os.path.exists(contact_path):
            os.makedirs(contact_path)
    
        # Environmental Auto-Detection
        hostname = socket.gethostname()
        if hostname.upper() == "GREENLANTERN" or os.path.exists(r"C:\FYRShare\Tools\FYRTools"):
            # Explicit central node network identity override
            my_ip = "192.168.0.108"
        else:
            # Resolve dynamic local LAN interface profile for clients
            my_ip = socket.gethostbyname(hostname)
            if my_ip == "127.0.0.1":
                # Fallback handler if system registers loopback as its primary interface address
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    my_ip = s.getsockname()[0]
                finally:
                    s.close()

        with open(os.path.join(contact_path, f"{alias}.contact"), "w") as f:
            f.write(f"{my_ip}:{PORT}|{status}")
            
        # Flush the matching offline flag payload if found in storage layers
        offline_path = os.path.join(contact_path, f"{alias}.offline")
        if os.path.exists(offline_path):
            os.remove(offline_path)
    except Exception as e:
        print(f"Warning: Could not announce presence. Shared drive might be offline. ({e})")

def remove_self(alias):
    """Removes the contact file and creates an offline marker."""
    contact_path = os.path.join(SHARED_PATH, "Contacts")
    try:
        file_path = os.path.join(contact_path, f"{alias}.contact")
        offline_path = os.path.join(contact_path, f"{alias}.offline")
        
        content = f"{socket.gethostbyname(socket.gethostname())}:{PORT}"
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                content = f.read().strip()
            os.remove(file_path)
            
        with open(offline_path, "w") as f:
            f.write(content)
    except Exception as e:
        print(f"Warning: Could not remove presence. ({e})")

def prune_attachments():
    """Removes attachments older than 30 days to save space."""
    att_path = os.path.join(SHARED_PATH, "Attachments")
    if not os.path.exists(att_path): return
    
    cutoff = time.time() - (30 * 86400) # 30 days in seconds
    
    try:
        files = os.listdir(att_path)
        total_files = len(files)
        
        window = None
        if total_files > 50:
            layout = [[sg.Text('Cleaning up old attachments...')],
                      [sg.ProgressBar(total_files, orientation='h', size=(30, 20), key='-PROG-')]]
            window = sg.Window('Startup Cleanup', layout, no_titlebar=True, keep_on_top=True, finalize=True, element_justification='c')

        for i, f in enumerate(files):
            if window and i % 5 == 0:
                window.read(timeout=0)
                window['-PROG-'].update(i + 1)

            f_path = os.path.join(att_path, f)
            try:
                if os.path.isfile(f_path):
                    if os.path.getmtime(f_path) < cutoff:
                        os.remove(f_path)
                        logging.info(f"Pruned old attachment: {f}")
            except Exception:
                pass
        
        if window:
            window.close()
    except Exception as e:
        logging.error(f"Pruning error: {e}")

def get_remote_contacts():
    """Reads all .contact files from the shared drive."""
    contact_path = os.path.join(SHARED_PATH, "Contacts")
    found_contacts = {}
    if os.path.exists(contact_path):
        for filename in os.listdir(contact_path):
            if filename.endswith(".contact"):
                alias = filename.replace(".contact", "")
                with open(os.path.join(contact_path, filename), "r") as f:
                    data = f.read().strip()
                    if ":" not in data:
                        data = f"{data}:5555"
                found_contacts[alias] = data
    return found_contacts

def get_offline_network_contacts():
    """Reads all .offline files from the shared drive."""
    contact_path = os.path.join(SHARED_PATH, "Contacts")
    found = set()
    if os.path.exists(contact_path):
        for filename in os.listdir(contact_path):
            if filename.endswith(".offline"):
                found.add(filename.replace(".offline", ""))
    return found

def log_msg(sender, recipient, message, direction):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # Store the encrypted version in the DB for security
    enc_msg = cipher.encrypt(message.encode()).decode()
    cur.execute("INSERT INTO messages (timestamp, sender, recipient, message, direction) VALUES (?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sender.strip(), recipient.strip(), enc_msg, direction))
    logging.info(f"DB Write: {direction} msg from {sender} to {recipient}")
    conn.commit()
    conn.close()

# --- WINDOW FLASHING ---
class FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint)]

def flash_window(window):
    if sys.platform == "win32":
        try:
            hwnd = ctypes.windll.user32.GetParent(window.TKroot.winfo_id())
            finfo = FLASHWINFO()
            finfo.cbSize = ctypes.sizeof(FLASHWINFO)
            finfo.hwnd = hwnd
            finfo.dwFlags = 3 | 12 # FLASHW_ALL | FLASHW_TIMERNOFG
            finfo.uCount = 0
            finfo.dwTimeout = 0
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(finfo))
        except Exception:
            pass

# --- NON-BLOCKING UI ACTIONS (SHAKE WINDOW) ---
def shake_window(window):
    """
    Executes a visual alert sequence (Nudge) by shifting the display coordinates.
    Spawns inside an isolated worker thread to decouple redraw overhead from the primary 
    GUI loop, preventing frame stutters on integrated GPU hardware.
    """
    if not window.TKroot or window.TKroot.state() == 'iconic':
        return
    
    def _shake():
        try:
            x, y = window.current_location()
            for _ in range(3):
                window.TKroot.geometry(f"+{x + 10}+{y}")
                time.sleep(0.04)
                window.TKroot.geometry(f"+{x - 10}+{y}")
                time.sleep(0.04)
            window.TKroot.geometry(f"+{x}+{y}")
        except:
            pass
            
    threading.Thread(target=_shake, daemon=True).start()

# --- NETWORKING & QUEUE ---
def open_url(event):
    """Opens a hyperlink when clicked in the chat window."""
    try:
        widget = event.widget
        index = widget.index(f"@{event.x},{event.y}")
        tags = widget.tag_names(index)
        if "URL" in tags:
            # Find the range of the URL containing the click index
            ranges = widget.tag_ranges("URL")
            for i in range(0, len(ranges), 2):
                start = ranges[i]
                end = ranges[i+1]
                if widget.compare(start, "<=", index) and widget.compare(end, ">", index):
                    url = widget.get(start, end)
                    if url.startswith("file:///"):
                        import urllib.parse
                        local_path = urllib.parse.unquote(url[8:]).replace("/", "\\")
                        os.startfile(local_path)
                    else:
                        webbrowser.open(url)
                    break
    except Exception as e:
        logging.error(f"URL Open Error: {e}")

def on_chat_right_click(event):
    """Custom right-click menu for the chat window to copy hyperlinks and text."""
    try:
        import tkinter as tk
        widget = event.widget
        index = widget.index(f"@{event.x},{event.y}")
        tags = widget.tag_names(index)
        
        menu = tk.Menu(widget, tearoff=0)
        
        if "URL" in tags:
            ranges = widget.tag_ranges("URL")
            for i in range(0, len(ranges), 2):
                start = ranges[i]
                end = ranges[i+1]
                if widget.compare(start, "<=", index) and widget.compare(end, ">", index):
                    url = widget.get(start, end)
                    def copy_link(u=url):
                        widget.clipboard_clear()
                        widget.clipboard_append(u)
                    menu.add_command(label="Copy Link", command=copy_link)
                    break
        
        def copy_selection():
            try:
                text = widget.selection_get()
                widget.clipboard_clear()
                widget.clipboard_append(text)
            except:
                pass
                
        def paste_selection():
            try:
                if widget['state'] == 'normal':
                    text = widget.clipboard_get()
                    widget.insert('insert', text)
            except:
                pass

        menu.add_command(label="Copy", command=copy_selection)
        menu.add_command(label="Paste", command=paste_selection)
        
        menu.post(event.x_root, event.y_root)
    except Exception as e:
        logging.error(f"Chat Right Click Error: {e}")
    return "break"

def print_chat_message(window, text, color, font):
    """Appends a message to the chat window with hyperlink detection."""
    try:
        widget = window["-CHAT-"].Widget
        is_disabled = widget['state'] == 'disabled'
        if is_disabled: widget.configure(state='normal')
            
        style_tag = f"style_{str(color).replace('#','').replace(' ','')}_{font[1]}"
        widget.tag_config(style_tag, foreground=color, font=font)
        
        # Detect [FILE] tag and convert to file:/// URL
        if "[FILE] " in text:
            parts_file = text.split("[FILE] ", 1)
            prefix = parts_file[0]
            new_name = parts_file[1].strip()
            
            # Form the full file path and quoted URL
            full_path = os.path.abspath(os.path.join(SHARED_PATH, "Attachments", new_name))
            import urllib.parse
            quoted_path = urllib.parse.quote(full_path.replace("\\", "/")).replace("%3A", ":").replace("%2F", "/")
            file_url = "file:///" + quoted_path
            text = f"{prefix}Sent file: {file_url}"

        parts = re.split(r'(https?://\S+|file:///\S+)', text)
        for part in parts:
            if re.match(r'(https?://\S+|file:///\S+)', part):
                widget.insert("end", part, (style_tag, "URL"))
            else:
                widget.insert("end", part, style_tag)
        widget.insert("end", "\n")
        if is_disabled: widget.configure(state='disabled')
        widget.see("end")
    except Exception as e:
        logging.error(f"Print Chat Error: {e}")

def listen_thread(window):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("0.0.0.0", PORT))
        server.listen(5)
        while True:
            client, addr = server.accept()
            data = client.recv(4096).decode("utf-8")
            if data:
                dec_payload = cipher.decrypt(data.encode()).decode()
                if "|" in dec_payload:
                    sender_name, msg_content = dec_payload.split("|", 1)
                else:
                    sender_name = addr[0]
                    msg_content = dec_payload
                log_msg(sender_name, my_alias, msg_content, "Received")
                window.write_event_value("-INCOMING-", (sender_name, msg_content)) # Trigger event in main loop
            client.close()
    except Exception as e:
        print(f"Listener Error: {e}")

def check_queue(window, unread_tracker):
    queue_dir = os.path.join(SHARED_PATH, "Queue")
    if not os.path.exists(queue_dir):
        try:
            os.makedirs(queue_dir)
        except:
            pass
    q_file = os.path.join(queue_dir, f"{my_alias}.txt")
    proc_file = q_file + ".processing"
    
    try:
        active = window["-USERS-"].get()
        active_user = active[0] if active else None
    except:
        active_user = None
        
    new_count = 0
    
    # Attempt to rename file to lock it for processing (prevents race conditions)
    if not os.path.exists(proc_file) and os.path.exists(q_file):
        try:
            os.rename(q_file, proc_file)
        except OSError:
            return 0 # File locked by writer
            
    try:
        if os.path.exists(proc_file):
            with open(proc_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        ts, sender, enc_msg = line.split("|", 2)
                        dec_payload = cipher.decrypt(enc_msg.encode()).decode()
                        # If payload contains Name|Message, strip the name since we have it from the file
                        if "|" in dec_payload and dec_payload.split("|", 1)[0] == sender:
                            _, real_msg = dec_payload.split("|", 1)
                        else:
                            real_msg = dec_payload
                            
                        log_msg(sender, my_alias, real_msg, "Received")
                        if active_user and sender == active_user:
                            print_chat_message(window, f"[{ts}] {sender}: {real_msg}", recv_col, (f_family, f_size))
                        else:
                            unread_tracker[sender] = unread_tracker.get(sender, 0) + 1
                        new_count += 1
                    except Exception:
                        continue # Skip malformed lines
            os.remove(proc_file)
            if new_count > 0:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                flash_window(window)
    except Exception as e:
        print(f"Queue check error: {e}")
    return new_count

def get_all_known_users():
    """Retrieves a set of all users found in the local chat history."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT sender FROM messages")
        senders = {r[0] for r in cur.fetchall() if r[0]}
        cur.execute("SELECT DISTINCT recipient FROM messages")
        recipients = {r[0] for r in cur.fetchall() if r[0]}
        conn.close()
        return (senders | recipients) - {my_alias, 'None', ''}
    except Exception:
        return set()

def get_chat_history(partner, partner_ip=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    # Fetch all messages and filter in Python to avoid complex SQL issues
    cur.execute("SELECT timestamp, sender, recipient, message FROM messages ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    
    filtered = []
    p_low = partner.lower().strip()
    m_low = my_alias.lower().strip()
    ip_low = partner_ip.lower().strip() if partner_ip else None
    debug_mismatches = []
    
    logging.debug(f"Scanning History for Partner='{p_low}' (IP={ip_low}) vs Me='{m_low}'")
    
    for row in rows:
        # row indices: 0=timestamp, 1=sender, 2=recipient, 3=message
        s = (row[1] or '').lower().strip()
        r = (row[2] or '').lower().strip()
        
        def is_partner(val):
            return val == p_low or (ip_low and val == ip_low)

        match = False
        # 1. Incoming: Sender is Partner, Recipient is Me (or NULL/Empty)
        if is_partner(s) and (r == m_low or r == '' or r == 'none'):
            match = True
            
        # 2. Outgoing: Sender is Me, Recipient is Partner (or NULL/Empty)
        elif s == m_low and (is_partner(r) or r == ''):
            match = True
            
        if match:
            filtered.append((row[0], row[1], row[3]))
        else:
            reason = f"Skip: s='{s}' r='{r}'"
            if len(debug_mismatches) < 10:
                debug_mismatches.append(reason)
            # Log first few mismatches to file to see why they fail
            if len(debug_mismatches) < 5:
                logging.debug(reason)

    return filtered, rows, debug_mismatches

def view_history():
    """Opens a window to view, manage, and delete chat history."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, timestamp, sender, recipient, direction, message FROM messages ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    data = []
    for row in rows:
        r_id, r_time, r_sender, r_recip, r_dir, r_msg = row
        try:
            dec = cipher.decrypt(r_msg.encode()).decode()
        except:
            dec = "<Error>"
        data.append([r_id, r_time, r_sender, r_recip, r_dir, dec])

    layout = [
        [sg.Table(values=data, headings=['ID', 'Time', 'Sender', 'Recipient', 'Dir', 'Message'],
                  auto_size_columns=False, col_widths=[5, 18, 15, 15, 8, 60],
                  justification='left', key='-HIST-', select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
                  enable_events=True, expand_x=True, expand_y=True)],
        [sg.Button('Delete Selected'), sg.Button('Delete All'), sg.Button('Close')]
    ]
    
    win = sg.Window("Message History", layout, size=(900, 500), modal=True, keep_on_top=True)
    
    while True:
        event, values = win.read()
        if event in (sg.WIN_CLOSED, 'Close'):
            break
            
        if event == 'Delete All':
            if sg.popup_yes_no("Delete ALL history?") == 'Yes':
                conn = sqlite3.connect(DB_FILE)
                conn.execute("DELETE FROM messages")
                conn.commit()
                conn.close()
                data = []
                win['-HIST-'].update(values=data)
                
        if event == 'Delete Selected':
            idxs = values['-HIST-']
            if idxs and sg.popup_yes_no(f"Delete {len(idxs)} messages?") == 'Yes':
                ids = [data[i][0] for i in idxs]
                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute(f"DELETE FROM messages WHERE id IN ({','.join(['?']*len(ids))})", ids)
                conn.commit()
                conn.close()
                
                for i in sorted(idxs, reverse=True):
                    del data[i]
                win['-HIST-'].update(values=data)
                
    win.close()



def create_alert_icon(path):
    """Generates a simple red dot icon if the file is missing."""
    if not os.path.exists(path):
        img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((2, 2, 30, 30), fill='red', outline='white')
        img.save(path)

def load_global_groups():
    path = os.path.join(SHARED_PATH, "global_groups.json")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_global_groups(groups):
    path = os.path.join(SHARED_PATH, "global_groups.json")
    try:
        with open(path, 'w') as f:
            json.dump(groups, f)
    except Exception as e:
        sg.popup_error(f"Could not save global groups: {e}")

def get_admin_password():
    """Reads the admin password from a local .env file."""
    env_path = os.path.join(script_dir, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                return f.read().strip()
        except:
            pass
    return None

def admin_panel(known_contacts):
    """Admin screen to manage groups."""
    
    # Handle both dict (online) and list (merged) inputs
    if isinstance(known_contacts, dict):
        contact_list = [u for u in known_contacts.keys() if u != my_alias]
    else:
        contact_list = [u for u in known_contacts if u != my_alias]
    
    def get_group_list_display():
        l_groups = sg.user_settings_get_entry('-GROUPS-', {})
        g_groups = load_global_groups()
        return [f"{k} (Local)" for k in l_groups] + [f"{k} (Global)" for k in g_groups]
    
    layout = [
        [sg.Text("Create New Group", font=("Bold", 12))],
        [sg.Text("Group Name:"), sg.Input(key='-GNAME-', size=(20,1)), sg.Checkbox("Make Global", key='-GLOBAL-')],
        [sg.Text("Select Members (Hold CTRL to select multiple):")],
        [sg.Listbox(contact_list, select_mode=sg.LISTBOX_SELECT_MODE_MULTIPLE, size=(30, 10), key='-GMEMBERS-')],
        [sg.Button("Save Group", bind_return_key=True), sg.Button("Delete Group"), sg.Button("Close")],
        [sg.HorizontalSeparator()],
        [sg.Text("Existing Groups:")],
        [sg.Listbox(get_group_list_display(), size=(30, 5), key='-GROUPS-', enable_events=True)]
    ]
    
    win = sg.Window("Admin Panel", layout, modal=True, finalize=True, keep_on_top=True)
    win['-GNAME-'].set_focus()

    while True:
        event, values = win.read()
        if event in (sg.WIN_CLOSED, 'Close'):
            break
            
        if event == '-GROUPS-':
            sel = values['-GROUPS-']
            if sel:
                group_str = sel[0]
                is_global = "(Global)" in group_str
                name = group_str.replace(" (Global)", "").replace(" (Local)", "")
                
                if is_global:
                    groups = load_global_groups()
                else:
                    groups = sg.user_settings_get_entry('-GROUPS-', {})
                
                members = groups.get(name, [])
                
                win['-GNAME-'].update(name)
                win['-GLOBAL-'].update(is_global)
                
                # Select members in listbox
                idxs = [i for i, c in enumerate(contact_list) if c in members]
                win['-GMEMBERS-'].update(set_to_index=idxs)

        if event == 'Save Group':
            name = values['-GNAME-']
            members = values['-GMEMBERS-']
            is_global = values['-GLOBAL-']
            if name and members:
                if is_global:
                    g_groups = load_global_groups()
                    g_groups[name] = members
                    save_global_groups(g_groups)
                else:
                    l_groups = sg.user_settings_get_entry('-GROUPS-', {})
                    l_groups[name] = members
                    sg.user_settings_set_entry('-GROUPS-', l_groups)
                
                win['-GROUPS-'].update(get_group_list_display())
                sg.popup(f"Group '{name}' saved!")
            else:
                sg.popup_error("Group Name and at least one Member are required.")
        if event == 'Delete Group':
            sel = values['-GROUPS-']
            if sel:
                group_str = sel[0]
                if sg.popup_yes_no(f"Delete group '{group_str}'?") == 'Yes':
                    if "(Global)" in group_str:
                        g_name = group_str.replace(" (Global)", "")
                        g_groups = load_global_groups()
                        if g_name in g_groups: del g_groups[g_name]
                        save_global_groups(g_groups)
                    else:
                        l_name = group_str.replace(" (Local)", "")
                        l_groups = sg.user_settings_get_entry('-GROUPS-', {})
                        if l_name in l_groups: del l_groups[l_name]
                        sg.user_settings_set_entry('-GROUPS-', l_groups)
                    
                    win['-GROUPS-'].update(get_group_list_display())

        if event == 'Update Password':
            new_pw = values['-NEWPW-']
            if new_pw:
                try:
                    env_path = os.path.join(script_dir, ".env")
                    with open(env_path, "w") as f:
                        f.write(new_pw)
                    sg.popup("Password updated successfully!")
                except Exception as e:
                    sg.popup_error(f"Failed to update password: {e}")
            else:
                sg.popup_error("Password cannot be empty.")
                
    win.close()

def get_contrast_text_color(hex_color):
    """Returns white or black text depending on background brightness."""
    if not hex_color or not hex_color.startswith('#'): return 'black'
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        lum = (0.299 * r + 0.587 * g + 0.114 * b)
        return 'black' if lum > 128 else 'white'
    except:
        return 'black'

# --- GUI DESIGN ---
def get_menu_def(size):
    size_opts = ['10', '12', '14', '16', '18', '20', '24']

    def check(val, curr):
        return f'!{val}' if str(val).lower() == str(curr).lower() else val

    admin_opt = 'Manage Groups'

    return [
        ['File', ['Minimize to Tray', 'Open Shared Files', 'Switch User', 'Exit']],
        ['Settings', ['Sent Color', 'Recv Color', 'App Theme Color',
                      'Font Size', [check(x, size) for x in size_opts]]],
        ['History', ['View History', 'Clear View']],
        ['Groups', [admin_opt]],
        ['Contacts', ['Refresh Contacts']]
    ]

def restart_application():
    """Restarts the application to apply changes."""
    try:
        if getattr(sys, 'frozen', False):
            args = [sys.executable] + sys.argv[1:]
        else:
            args = [sys.executable] + sys.argv
        
        subprocess.Popen(args)
        sys.exit()
    except Exception as e:
        logging.error(f"Restart failed: {e}")
        sys.exit()

def launch_wysiwyg():
    """Launches the main Wysiwyg web server application."""
    exe_path = r"C:\FYRTOOLS\WYSIWYG\WYSIWYG.exe"
    if os.path.exists(exe_path):
        try:
            subprocess.Popen(exe_path, cwd=os.path.dirname(exe_path))
            return True
        except Exception as e:
            logging.error(f"Failed to launch Wysiwyg EXE: {e}")
            
    # Dev mode fallback: look for main.py in the parent directory
    dev_script = os.path.abspath(os.path.join(script_dir, "..", "main.py"))
    if os.path.exists(dev_script):
        try:
            # Run using the current virtual environment's python interpreter
            subprocess.Popen([sys.executable, dev_script], cwd=os.path.dirname(dev_script))
            return True
        except Exception as e:
            logging.error(f"Failed to launch Wysiwyg script: {e}")
            
    return False

def launch_wysiscan():
    exe_path = r"C:\FYRTOOLS\WysiScan\WysiScan.exe"
    if os.path.exists(exe_path):
        try:
            subprocess.Popen(exe_path, cwd=os.path.dirname(exe_path))
            return True
        except Exception as e:
            logging.error(f"Failed to launch WysiScan EXE: {e}")
    dev_script = os.path.abspath(os.path.join(script_dir, "..", "WysiScan", "scanner_server.py"))
    if os.path.exists(dev_script):
        try:
            subprocess.Popen([sys.executable, dev_script], cwd=os.path.dirname(dev_script))
            return True
        except Exception as e:
            logging.error(f"Failed to launch WysiScan script: {e}")
    return False


# --- MAIN LOOP ---
def main():
    global sent_col, recv_col, f_size
    init_db()
    prune_attachments() # Clean up old files on startup
    
    # --- THEME SETUP ---
    app_bg = sg.user_settings_get_entry('-APP-BG-', None)
    use_custom_title = False
    if app_bg:
        txt_col = get_contrast_text_color(app_bg)
        # Define a custom theme based on user selection
        sg.theme_add_new('UserTheme', {
            'BACKGROUND': app_bg,
            'TEXT': txt_col,
            'INPUT': '#ffffff',
            'TEXT_INPUT': '#000000',
            'SCROLL': txt_col,
            'BUTTON': ('white', '#333333'),
            'PROGRESS': ('#01826B', '#D0D0D0'),
            'BORDER': 1, 'SLIDER_DEPTH': 0, 'PROGRESS_DEPTH': 0,
        })
        sg.theme('UserTheme')
        use_custom_title = True

    # Initialize networking/contacts
    announce_self(my_alias)
    
    # --- HELPER: Refresh List ---
    def refresh_contact_list():
        r_contacts = get_remote_contacts()
        d_users = get_all_known_users()
        o_users = get_offline_network_contacts()
        
        # Merge Online, Database History, and Network Offline files
        all_people = sorted(list(set(r_contacts.keys()) | d_users | o_users))
        
        l_groups = sg.user_settings_get_entry('-GROUPS-', {})
        g_groups = load_global_groups()
        a_groups = {**l_groups, **g_groups}
        
        d_list = [f"*{g}" for g in a_groups.keys()] + [u for u in all_people if u != my_alias]
        return r_contacts, d_list, a_groups

    remote_contacts, display_list, all_groups = refresh_contact_list()
    
    unread_per_user = {}
    
    start_minimized = sg.user_settings_get_entry('-START-MIN-', False)

    right_click_menu = ['', ['Copy', 'Paste']]
    contact_rc_menu = ['', ['Nudge']]

    def update_unread_ui():
        """Updates the listbox text color based on unread status."""
        try:
            current_list = window["-USERS-"].get_list_values()
            
            # Recalculate text color based on current theme background
            app_bg = sg.user_settings_get_entry('-APP-BG-', '#ffffff')
            txt_col = get_contrast_text_color(app_bg)
            offline_col = 'grey' if txt_col == 'black' else "#868184" # grey for Offline
            
            for i, item in enumerate(current_list):
                if item in unread_per_user and unread_per_user[item] > 0:
                    window["-USERS-"].Widget.itemconfig(i, {'fg': '#FF4500'}) # OrangeRed for unread
                elif item in remote_contacts or item.startswith("*"):
                    # Check for AFK
                    is_afk = False
                    if item in remote_contacts:
                        val = remote_contacts[item]
                        if "|Away" in val:
                            is_afk = True
                    
                    if is_afk:
                        window["-USERS-"].Widget.itemconfig(i, {'fg': '#DAA520'}) # Goldenrod for AFK
                    else:
                        window["-USERS-"].Widget.itemconfig(i, {'fg': txt_col}) # Normal for Online/Groups
                else:
                    window["-USERS-"].Widget.itemconfig(i, {'fg': offline_col}) # Faded for Offline
        except Exception:
            pass

    # Define Layout inside main to support dynamic theme changes
    contacts = {} 
    layout = [
        [sg.MenubarCustom(get_menu_def(f_size), key='-MENU-')],
        [sg.Text(f"Chatting as: {my_alias}", font=(f_family, 10, "bold")), sg.Push(), sg.Checkbox("AFK", key='-AFK-', enable_events=True), sg.Checkbox("Start Minimized", default=start_minimized, key='-START-MIN-', enable_events=True)],
        [sg.Col([[sg.Text("Contacts")],
                 [sg.Listbox(list(contacts.keys()), size=(15, 15), key="-USERS-", enable_events=True, expand_y=True, right_click_menu=contact_rc_menu)]], key='-COL-USERS-', expand_y=True, expand_x=False, pad=((5, 5), (0, 5))),
         sg.Col([[sg.Text("Chatting with: "), sg.Text("None", key="-TARGET-", text_color="yellow")],
                 [sg.Multiline(size=(50, 15), key="-CHAT-", disabled=True, font=(f_family, f_size), expand_x=True, expand_y=True, right_click_menu=right_click_menu)],
                 [sg.Input(key="-IN-", size=(30, 1), expand_x=True, right_click_menu=right_click_menu), sg.Button("Send", bind_return_key=True), sg.Button("Attach"), sg.Button("Clear")]], key='-COL-CHAT-', expand_x=True, expand_y=True, pad=((0, 5), (0, 5)))]
    ]

    # --- Icon Loading ---
    # To prevent crashes with PyInstaller's _MEIPASS temp folder, we load the icons
    # into bytes objects at startup and pass the data directly to the Image elements.
    # This avoids passing file paths that can become invalid or inaccessible.
    window_icon_path = resource_path("fyrlogo.png")
    alert_icon_path = os.path.join(script_dir, "fyrlogo_alert.png")
    create_alert_icon(alert_icon_path)

    tray_icon_bytes = None
    try:
        with open(window_icon_path, 'rb') as f:
            tray_icon_bytes = f.read()
    except Exception as e:
        logging.error(f"Fatal: Could not load tray icon from {window_icon_path}: {e}")
        sg.popup_error(f"Fatal: Could not load tray icon.\n{e}", keep_on_top=True)
        sys.exit()

    alert_icon_bytes = None
    try:
        with open(alert_icon_path, 'rb') as f:
            alert_icon_bytes = f.read()
    except Exception as e:
        logging.warning(f"Could not load alert icon from {alert_icon_path}: {e}")
    
    win_loc = sg.user_settings_get_entry('-WIN-LOC-', None)
    win_size = sg.user_settings_get_entry('-WIN-SIZE-', None)
    
    window = sg.Window("WysiChat", layout, finalize=True, icon=window_icon_path, resizable=True, use_custom_titlebar=use_custom_title, enable_close_attempted_event=True, location=win_loc if win_loc else (None, None), size=win_size if win_size else (None, None), keep_on_top=True)
    window.TKroot.bind('<Enter>', lambda e: window.bring_to_front())
    window['-IN-'].bind('<Button-1>', 'ResetUnread')
    window['-CHAT-'].bind('<Button-1>', 'ResetUnread')
    
    # Configure URL tag and bindings
    chat_widget = window["-CHAT-"].Widget
    chat_widget.tag_config("URL", foreground="blue", underline=True)
    chat_widget.tag_bind("URL", "<Button-1>", open_url)
    chat_widget.tag_bind("URL", "<Button-2>", open_url)
    chat_widget.tag_bind("URL", "<Enter>", lambda e: chat_widget.config(cursor="hand2"))
    chat_widget.tag_bind("URL", "<Leave>", lambda e: chat_widget.config(cursor=""))
    chat_widget.bind("<Button-3>", on_chat_right_click)

    # Configure element expansion for resizing
    try:
        if "-COL-USERS-" in window.AllKeysDict:
            window["-COL-USERS-"].expand(expand_x=False, expand_y=True)
        if "-USERS-" in window.AllKeysDict:
            window["-USERS-"].expand(expand_x=True, expand_y=True)
        if "-COL-CHAT-" in window.AllKeysDict:
            window["-COL-CHAT-"].expand(expand_x=True, expand_y=True)
        if "-CHAT-" in window.AllKeysDict:
            window["-CHAT-"].expand(expand_x=True, expand_y=True)
        if "-IN-" in window.AllKeysDict:
            window["-IN-"].expand(expand_x=True, expand_y=False)
    except Exception as e:
        logging.error(f"Error configuring element expansion: {e}")


    # Auto-refresh the list immediately after window creation
    window["-USERS-"].update(display_list)
    update_unread_ui()

    current_chat_target = None

    # --- HELPER: Load Chat for Target ---
    def load_chat(target):
        nonlocal current_chat_target
        logging.info(f"--- UI Load Chat: {target} ---")
        window["-TARGET-"].update(target)
        window["-CHAT-"].update(disabled=False) # Enable first
        window["-CHAT-"].update("") # Then Clear
        window.refresh() # Force GUI to process the 'enabled' state
        unread_per_user[target] = 0
        update_unread_ui()
        current_chat_target = target
        
        # Try to resolve IP to match old messages stored by IP
        target_ip = None
        if target in remote_contacts:
            target_ip = remote_contacts[target].split(":")[0]

        if not target.startswith("*"):
            hist, all_rows, debug_misses = get_chat_history(target, target_ip)
            logging.info(f"Found {len(hist)} valid messages out of {len(all_rows)} total DB rows.")
            if not hist:
                print_chat_message(window, f"--- No history found with {target} ---", "gray", (f_family, f_size))
            else:
                for row in hist:
                    ts, sender, enc_msg = row
                    try:
                        dec_msg = cipher.decrypt(enc_msg.encode()).decode()
                        # Ensure colors are valid
                        s_color = sent_col if sent_col and str(sent_col).lower() != 'none' else 'blue'
                        r_color = recv_col if recv_col and str(recv_col).lower() != 'none' else 'green'
                        
                        if sender == my_alias:
                            print_chat_message(window, f"[{ts}] Me: {dec_msg}", s_color, (f_family, f_size))
                        else:
                            print_chat_message(window, f"[{ts}] {sender}: {dec_msg}", r_color, (f_family, f_size))
                    except Exception as e:
                        logging.error(f"Decryption error for row {row}: {e}")
                        print_chat_message(window, f"[{ts}] {sender}: <Encrypted Message: {e}>", "red", (f_family, f_size))
                        
        window["-CHAT-"].update(disabled=True) # Re-disable (Read Only)
        window["-CHAT-"].set_vscroll_position(1.0) # Scroll to bottom

    # --- AUTO-LOAD LAST USER ---
    last_partner = sg.user_settings_get_entry('-LAST-PARTNER-', None)
    if last_partner and last_partner in display_list:
        # Select the user in the listbox visually
        try:
            idx = display_list.index(last_partner)
            window["-USERS-"].update(set_to_index=idx)
            load_chat(last_partner)
        except:
            pass

    # --- TRAY REPLACEMENT (Floating Window) ---
    def create_tray_window():
        loc = sg.user_settings_get_entry('-TRAY-LOC-', (None, None))
        menu = ['', ['Restore', 'Run Wysiwyg', 'Wysiscanner', 'Update Apps', 'Exit']]
        
        # Use Magenta as transparency key to hide the window background
        bg_col = '#ff00ff'
        layout = [[sg.Image(data=tray_icon_bytes, key='-TRAY-IMG-', background_color=bg_col, right_click_menu=menu, tooltip='WysiChat')]]
        w = sg.Window('WysiChat Bubble', layout, no_titlebar=True, keep_on_top=True, grab_anywhere=True, location=loc, finalize=True, margins=(0,0), element_padding=(0,0), background_color=bg_col, transparent_color=bg_col)
        w['-TRAY-IMG-'].bind('<Double-Button-1>', '_DOUBLE')
        return w

    tray_window = create_tray_window()
    if start_minimized:
        window.hide()
        tray_window.un_hide()
    else:
        tray_window.hide() # Start hidden
    
    threading.Thread(target=listen_thread, args=(window,), daemon=True).start()
    
    flash_state = False
    flash_timer = 0
    refresh_timer = 0
    queue_timer = 0
    unread_count = 0
    tray_flashing = False

    def send_payload(target_name, target_address, text_content):
        """Helper to encrypt and send data via Socket or File Queue."""
        # Handle Status suffix if present (IP:PORT|Status)
        clean_addr = target_address.split("|")[0]
        if ":" in clean_addr:
            target_ip, target_port = clean_addr.split(":")
            target_port = int(target_port)
        else:
            target_ip = clean_addr
            target_port = 5555

        # Embed sender name in payload so receiver knows who it is (resolves IP issues)
        full_payload = f"{my_alias}|{text_content}"
        enc_msg = cipher.encrypt(full_payload.encode()).decode()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((target_ip, target_port))
            s.send(enc_msg.encode())
            s.close()
            status = "Direct"
        except:
            queue_dir = os.path.join(SHARED_PATH, "Queue")
            if not os.path.exists(queue_dir): os.makedirs(queue_dir)
            with open(os.path.join(queue_dir, f"{target_name}.txt"), "a") as f:
                f.write(f"{datetime.now().strftime('%H:%M')}|{my_alias}|{enc_msg}\n")
            status = "Queued"

        log_msg(my_alias, target_name, text_content, "Sent")
        
        active = window["-USERS-"].get()
        if active and active[0] == target_name:
            print_chat_message(window, f"Me ({status}): {text_content}", sent_col, (f_family, f_size))

    def send_file_helper(target_name, file_path):
        """Handles copying file to shared drive and sending notification."""
        if target_name.startswith("*"):
            sg.popup_error("Attachments are not supported for Groups yet.")
            return

        if target_name in remote_contacts:
            target_ip = remote_contacts[target_name]
        else:
            target_ip = "0.0.0.0" # Offline attachment send
            
        try:
            att_path = os.path.join(SHARED_PATH, "Attachments")
            if not os.path.exists(att_path): os.makedirs(att_path)
            
            # Create unique name: Sender_Timestamp_Filename
            base_name = os.path.basename(file_path)
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{MY_NAME}_{ts_str}_{base_name}"
            
            shutil.copy(file_path, os.path.join(att_path, new_name))
            send_payload(target_name, target_ip, f"[FILE] {new_name}")
        except Exception as e:
            sg.popup_error(f"Failed to attach file: {e}")

    def save_loc():
        try:
            if window.TKroot and window.TKroot.state() == 'normal':
                # Parse geometry manually to avoid issues with minimized windows
                geo = window.TKroot.geometry() # Format is WxH+X+Y
                parts = geo.replace('x', '+').split('+')
                if len(parts) >= 4:
                    w, h, x, y = map(int, parts)
                    sg.user_settings_set_entry('-WIN-LOC-', (x, y))
                    sg.user_settings_set_entry('-WIN-SIZE-', (w, h))
            if tray_window and tray_window.TKroot:
                geo = tray_window.TKroot.geometry()
                parts = geo.replace('x', '+').split('+')
                if len(parts) >= 4:
                    x, y = int(parts[2]), int(parts[3])
                    if x > -10000 and y > -10000:
                        sg.user_settings_set_entry('-TRAY-LOC-', (x, y))
        except:
            pass

    while True:
        event, values = window.read(timeout=100) # Poll faster for tray responsiveness
        
        if event not in (sg.TIMEOUT_EVENT, '__TIMEOUT__'):
            logging.debug(f"Event Fired: {event}")
        
        # --- Handle Drag & Drop Event ---
        # if event == '-DROP-':
        #     if values['-DROP-'] and values["-USERS-"]:
        #         # Parse file list (handles paths with spaces/braces)
        #         file_list = window.TKroot.tk.splitlist(values['-DROP-'])
        #         target = values["-USERS-"][0]
        #         for f_path in file_list:
        #             if os.path.exists(f_path):
        #                 send_file_helper(target, f_path)
        #     elif not values["-USERS-"]:
        #         sg.popup_error("Please select a contact to send the file to.")

        # Check for file drop (Event is a path string)
        if event and isinstance(event, str) and (os.path.exists(event) or (";" in event and os.path.exists(event.split(";")[0]))):
            if not values["-USERS-"]:
                sg.popup_error("Please select a contact to send the file to.")
                continue
            
            # Handle potential multiple files (FreeSimpleGUI often separates by ;)
            files = event.split(";")
            for f_path in files:
                f_path = f_path.strip()
                if os.path.exists(f_path):
                    send_file_helper(values["-USERS-"][0], f_path)
        
        if event == '-AFK-':
            is_afk = values['-AFK-']
            status = "Away" if is_afk else "Online"
            announce_self(my_alias, status)
            # Force refresh to update own color immediately
            remote_contacts, display_list, all_groups = refresh_contact_list()
            update_unread_ui()

        if event == '-START-MIN-':
            sg.user_settings_set_entry('-START-MIN-', values['-START-MIN-'])
        
        # --- Handle Settings Changes ---
        if event == 'Sent Color':
            color_resp = sg.askcolor(color=sent_col, title="Sent Color")
            if color_resp and color_resp[1]:
                sent_col = color_resp[1]
                sg.user_settings_set_entry('-SENT-COLOR-', sent_col)

        if event == 'Recv Color':
            color_resp = sg.askcolor(color=recv_col, title="Recv Color")
            if color_resp and color_resp[1]:
                recv_col = color_resp[1]
                sg.user_settings_set_entry('-RECV-COLOR-', recv_col)

        if event == 'App Theme Color':
            color_resp = sg.askcolor(color=app_bg if app_bg else '#ffffff', title="App Background")
            if color_resp and color_resp[1]:
                new_bg = color_resp[1]
                sg.user_settings_set_entry('-APP-BG-', new_bg)
                if sg.popup_yes_no("Restart to apply theme?") == 'Yes':
                    save_loc()
                    window.close()
                    tray_window.close()
                    restart_application()

        if event in ('10', '12', '14', '16', '18', '20', '24'):
            f_size = int(event)
            sg.user_settings_set_entry('-FONT-SIZE-', f_size)
            window['-CHAT-'].update(font=(f_family, f_size))
            window['-MENU-'].update(get_menu_def(f_size))

        # Check Tray Window Events
        tray_event, tray_values = tray_window.read(timeout=0)
        if tray_event == 'Exit':
            save_loc()
            break
        if tray_event == 'Run Wysiwyg':
            launch_wysiwyg()
        if tray_event == 'Wysiscanner':
            launch_wysiscan()



        if tray_event == 'Update Apps':
            layout = [
                [sg.Text("Select application to update:")],
                [sg.Radio("Wysiwyg", "RADIO1", default=True, key="-UPDATE-WYSIWYG-")],
                [sg.Radio("WysiScan", "RADIO1", key="-UPDATE-WYSISCAN-")],
                [sg.Radio("WysiChat", "RADIO1", key="-UPDATE-WYSICHAT-")],
                [sg.Button("Ok"), sg.Button("Cancel")]
            ]
            update_win = sg.Window("Update Apps", layout, modal=True, keep_on_top=True)
            u_event, u_values = update_win.read()
            update_win.close()

            if u_event == "Ok":
                installer_path = None
                if u_values.get("-UPDATE-WYSIWYG-"):
                    installer_path = os.path.join(FYRTOOLS_ROOT, "WYSIWYG", "INSTALL_WYSIWYG.exe")
                elif u_values.get("-UPDATE-WYSISCAN-"):
                    installer_path = os.path.join(FYRTOOLS_ROOT, "WysiScan", "INSTALL_WYSISCAN.exe")
                elif u_values.get("-UPDATE-WYSICHAT-"):
                    installer_path = os.path.join(SHARED_PATH, "INSTALL_WYSICHAT.exe")
                    # Check version from shared drive
                    try:
                        v_path = os.path.join(SHARED_PATH, "version.txt")
                        if os.path.exists(v_path):
                            with open(v_path, 'r') as f:
                                remote_ver = f.read().strip()
                            if remote_ver == APP_VERSION:
                                if sg.popup_yes_no(f"You have the latest version ({APP_VERSION}). Re-install anyway?", title="Update Check") != 'Yes':
                                    installer_path = None
                    except Exception:
                        pass
                
                if installer_path:
                    if os.path.exists(installer_path):
                        try:
                            # Use ShellExecuteW with "runas" to request admin rights
                            ctypes.windll.shell32.ShellExecuteW(None, "runas", installer_path, None, None, 1)
                        except Exception as e:
                            sg.popup_error(f"Failed to start installer: {e}")
                    else:
                        sg.popup_error(f"Installer not found:\n{installer_path}")

        if tray_event in ('Restore', '-TRAY-IMG-_DOUBLE'):
            window.un_hide()
            window.keep_on_top_set()
            window.bring_to_front()
            tray_window.hide()
            
            # Auto-open chat if there are unread messages
            if unread_count > 0:
                target_user = None
                for user, count in unread_per_user.items():
                    if count > 0:
                        target_user = user
                        break
                
                if target_user:
                    try:
                        curr_list = window["-USERS-"].get_list_values()
                        if target_user in curr_list:
                            idx = curr_list.index(target_user)
                            window["-USERS-"].update(set_to_index=idx)
                            sg.user_settings_set_entry('-LAST-PARTNER-', target_user)
                    except:
                        pass
                    load_chat(target_user)

            tray_flashing = False
            try:
                tray_window['-TRAY-IMG-'].update(data=tray_icon_bytes)
            except Exception:
                pass
            unread_count = 0
            tray_window['-TRAY-IMG-'].set_tooltip('WysiChat Bubble')
            
            unread_count = sum(unread_per_user.values())
            if unread_count > 0:
                tray_window['-TRAY-IMG-'].set_tooltip(f'WysiChat ({unread_count} unread)')
            else:
                tray_window['-TRAY-IMG-'].set_tooltip('WysiChat')

        if event == "Exit":
            save_loc()
            break

        if event == "Open Shared Files":
            att_path = os.path.join(SHARED_PATH, "Attachments")
            if not os.path.exists(att_path): os.makedirs(att_path)
            os.startfile(att_path)

        if event == "Switch User":
            if sg.popup_yes_no("Switch User? This will restart the application.") == "Yes":
                save_loc()
                remove_self(my_alias)
                sg.user_settings_filename(filename=f'machine_conf_{MY_NAME}.json', path='.')
                sg.user_settings_set_entry('-LAST-USER-', None)
                window.close()
                tray_window.close()
                restart_application()

        if event == 'ResetUnread':
            tray_flashing = False
            try:
                tray_window['-TRAY-IMG-'].update(data=tray_icon_bytes)
            except Exception:
                pass
            unread_count = 0
            tray_window['-TRAY-IMG-'].set_tooltip('WysiChat')

        if event == sg.WIN_CLOSED:
            save_loc()
            break

        # Catch standard minimize event (user clicked '_') and send to tray
        try:
            if window.TKroot.state() == 'iconic':
                save_loc() # Save before hiding
                window.hide()
                tray_window.un_hide()
                continue
        except Exception:
            pass

        if event in (sg.WINDOW_CLOSE_ATTEMPTED_EVENT, "Minimize to Tray"):
            save_loc() # Save before hiding
            window.hide()
            tray_window.un_hide()
            continue
        if event == sg.TIMEOUT_EVENT:
            # Auto-Refresh Contacts every 5 seconds
            refresh_timer += 100
            if refresh_timer >= 5000:
                remote_contacts, display_list, all_groups = refresh_contact_list()
                
                # Preserve selection
                sel = window["-USERS-"].get()
                window["-USERS-"].update(display_list)
                if sel and sel[0] in display_list:
                    window["-USERS-"].update(set_to_index=display_list.index(sel[0]))
                    
                update_unread_ui()
                refresh_timer = 0

            queue_timer += 100
            if queue_timer >= 1000:
                new_msgs = check_queue(window, unread_per_user)
                if new_msgs > 0:
                    unread_count += new_msgs
                    tray_window['-TRAY-IMG-'].set_tooltip(f'WysiChat ({unread_count} unread)')
                    tray_flashing = True
                    update_unread_ui()
                queue_timer = 0
            
            # Blinking Logic
            if tray_flashing:
                flash_timer += 100
                if flash_timer >= 500: # Toggle every 500ms
                    flash_timer = 0
                    flash_state = not flash_state
                    new_icon_data = alert_icon_bytes if flash_state and alert_icon_bytes else tray_icon_bytes
                    try:
                        tray_window['-TRAY-IMG-'].update(data=new_icon_data)
                    except Exception:
                        pass # Ignore icon update errors (e.g. if .ico fails to load)
            continue

        if event == "Refresh Contacts":
            remote_contacts, display_list, all_groups = refresh_contact_list()
            
            # Preserve selection
            sel = window["-USERS-"].get()
            window["-USERS-"].update(display_list)
            if sel and sel[0] in display_list:
                window["-USERS-"].update(set_to_index=display_list.index(sel[0]))
                
            update_unread_ui()

        if event == "Manage Groups":
            # Pass all known people so we can add offline users to groups
            all_known_people = sorted(list(set(remote_contacts.keys()) | get_all_known_users() | get_offline_network_contacts()))
            admin_panel(all_known_people)
            # Auto refresh after admin panel closes to show new groups
            remote_contacts, display_list, all_groups = refresh_contact_list()
            
            # Preserve selection
            sel = window["-USERS-"].get()
            window["-USERS-"].update(display_list)
            if sel and sel[0] in display_list:
                window["-USERS-"].update(set_to_index=display_list.index(sel[0]))
                
            update_unread_ui()

        if event == "-USERS-":
            if not values["-USERS-"]:
                continue
            target = values["-USERS-"][0]
            sg.user_settings_set_entry('-LAST-PARTNER-', target) # Save selection
            window["-IN-"].set_focus()
            load_chat(target)

        if event == "Send" and values["-USERS-"]:
            target_selection = values["-USERS-"][0]
            msg = values["-IN-"]
            
            # Ensure chat is loaded for this user (fixes issue if selection event was missed)
            if current_chat_target != target_selection:
                load_chat(target_selection)
            
            if msg:
                # Check if it is a Group (starts with *)
                if target_selection.startswith("*"):
                    g_name = target_selection[1:] # Remove *
                    local_groups = sg.user_settings_get_entry('-GROUPS-', {})
                    global_groups = load_global_groups()
                    all_groups = {**local_groups, **global_groups}
                    if g_name in all_groups:
                        members = all_groups[g_name]
                        print_chat_message(window, f"--- Sending to Group: {g_name} ---", "yellow", (f_family, f_size))
                        for member in members:
                            if member in remote_contacts:
                                send_payload(member, remote_contacts[member], msg)
                            else:
                                # Send to offline queue
                                send_payload(member, "0.0.0.0", msg)
                else:
                    # Single User
                    if target_selection in remote_contacts:
                        send_payload(target_selection, remote_contacts[target_selection], msg)
                    else:
                        # Offline send
                        send_payload(target_selection, "0.0.0.0", msg)

                window["-IN-"].update("")

        if event == "Attach" and values["-USERS-"]:
            target_selection = values["-USERS-"][0]
            filename = sg.popup_get_file("Select file to send", no_window=True)
            if filename:
                send_file_helper(target_selection, filename)

        if event == "Clear":
            window["-CHAT-"].update(disabled=False)
            window["-CHAT-"].update("")
            window["-CHAT-"].update(disabled=True)

        if event == "Nudge" and values["-USERS-"]:
            target = values["-USERS-"][0]
            if target.startswith("*"):
                sg.popup_error("Cannot nudge a group.")
            else:
                if target in remote_contacts:
                    send_payload(target, remote_contacts[target], "[NUDGE]")
                else:
                    send_payload(target, "0.0.0.0", "[NUDGE]")

        if event == "-INCOMING-":
            sender_ip, msg = values[event]
            
            active = window["-USERS-"].get()
            if active and active[0] == sender_ip:
                print_chat_message(window, f"{sender_ip}: {msg}", recv_col, (f_family, f_size))
            else:
                if msg != "[NUDGE]":
                    unread_per_user[sender_ip] = unread_per_user.get(sender_ip, 0) + 1
                    update_unread_ui()
                
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            if msg == "[NUDGE]":
                shake_window(window)
            else:
                flash_window(window)
            unread_count += 1
            tray_window['-TRAY-IMG-'].set_tooltip(f'WysiChat ({unread_count} unread)')
            tray_flashing = True

        if event == "View History":
            view_history()


        if event == 'Copy':
            try:
                elem = window.find_element_with_focus()
                if elem and elem.Widget:
                    text = elem.Widget.selection_get()
                    window.TKroot.clipboard_clear()
                    window.TKroot.clipboard_append(text)
            except Exception:
                pass

        if event == 'Paste':
            try:
                elem = window.find_element_with_focus()
                if elem and elem.Widget:
                    widget = elem.Widget
                    if widget['state'] == 'normal':
                        text = window.TKroot.clipboard_get()
                        widget.insert('insert', text)
            except Exception:
                pass

    remove_self(my_alias) # Ensure we mark ourselves as offline on exit
    tray_window.close()
    window.close()

if __name__ == "__main__":
    # Prevent multiple instances of WysiChat
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        global _wysichat_instance_mutex
        _wysichat_instance_mutex = kernel32.CreateMutexW(None, False, "Local\\WYSICHAT_SINGLE_INSTANCE_MUTEX")
        last_error = ctypes.get_last_error()
        if last_error in (5, 183):  # ERROR_ACCESS_DENIED or ERROR_ALREADY_EXISTS
            sys.exit(0)
    main()
