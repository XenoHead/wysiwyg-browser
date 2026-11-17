r"""WYSIWYG Patch Tool - a small Tk GUI around make_patch.ps1 / apply_patch.ps1.
Build a loose-file patch (no reinstall), or apply one to this machine.
Everything it runs is the same script the README describes; the GUI only
collects the arguments and shows the output.

Run with:  patches\Patch GUI.bat   (or: python patches\patch_gui.py)
"""

import datetime
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

PATCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(PATCH_DIR)
VERSION_FILE = os.path.join(REPO_ROOT, "version.json")
ISS_FILE = os.path.join(REPO_ROOT, "wysiWyg-installer.iss")
CHANGELOG_FILE = os.path.join(REPO_ROOT, "changelog.txt")
MAKE_PS1 = os.path.join(PATCH_DIR, "make_patch.ps1")
APPLY_PS1 = os.path.join(PATCH_DIR, "apply_patch.ps1")
BUILD_FULL_PS1 = os.path.join(PATCH_DIR, "build_full.ps1")
OUT_ROOT = os.path.join(PATCH_DIR, "out")
DEFAULT_SHARE = r"\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG"
DEFAULT_INSTALL = r"C:\FYRTOOLS\WYSIWYG"
INNO_APP_ID = r"{C349C35F-55AA-466D-B029-6D39D55C0E28}_is1"

BG = "#15151b"
PANEL = "#1e1e26"
LOG_BG = "#101016"
FG = "#ffffff"
MUTED = "#9a9aa5"
ACCENT = "#0078d7"
OK = "#3fb950"
WARN = "#d29922"
ERR = "#f85149"

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_H1 = ("Segoe UI", 15, "bold")
FONT_MONO = ("Consolas", 9)

CREATE_NO_WINDOW = 0x08000000


# --- helpers ----------------------------------------------------------------
def ps_command(script, args):
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", script] + args


def read_version(path=VERSION_FILE):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def version_str(v):
    return "{0}.{1}.{2}.{3}".format(int(v.get("major", 0)), int(v.get("minor", 0)),
                                    int(v.get("patch", 0)), int(v.get("build", 0)))


def list_changes():
    proc = subprocess.run(ps_command(MAKE_PS1, ["-List"]), cwd=REPO_ROOT,
                          capture_output=True, text=True, errors="replace",
                          creationflags=CREATE_NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError((proc.stdout or "") + (proc.stderr or ""))
    text = proc.stdout.strip()
    start = text.find("{")
    if start < 0:
        raise RuntimeError("Unexpected output from make_patch.ps1 -List:\n" + text)
    return json.loads(text[start:])


def detect_install_dir():
    try:
        import winreg

        key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + INNO_APP_ID
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, 0,
                                    winreg.KEY_READ | view) as handle:
                    loc, _ = winreg.QueryValueEx(handle, "InstallLocation")
                    if loc:
                        loc = loc.rstrip("\\")
                        if os.path.exists(os.path.join(loc, "WYSIWYG.exe")):
                            return loc
            except OSError:
                pass
    except Exception:
        pass
    return DEFAULT_INSTALL


class ScrollFrame(ttk.Frame):
    """A vertically scrollable frame (for the file check list)."""

    def __init__(self, master, height=210, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, height=height)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", self._grab_wheel)
        self.canvas.bind("<Leave>", self._release_wheel)

    def _on_inner(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _grab_wheel(self, _event):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _release_wheel(self, _event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()


def make_log(parent, height=9):
    frame = ttk.Frame(parent)
    text = tk.Text(frame, height=height, bg=LOG_BG, fg=FG, insertbackground=FG,
                   relief="flat", font=FONT_MONO, wrap="word", padx=10, pady=8,
                   state="disabled")
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    text.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    text.tag_configure("ok", foreground=OK)
    text.tag_configure("warn", foreground=WARN)
    text.tag_configure("err", foreground=ERR)
    text.tag_configure("muted", foreground=MUTED)
    return frame, text


# --- app --------------------------------------------------------------------
class PatchTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WYSIWYG Patch Tool")
        self.geometry("1000x760")
        self.minsize(880, 640)
        self.configure(bg=BG)
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        try:
            self.iconbitmap(os.path.join(REPO_ROOT, "fyrlogo.ico"))
        except Exception:
            pass

        self.jobs = queue.Queue()
        self.file_vars = {}
        self.busy = False
        self.last_build_dir = None

        self._init_style()
        self._build_header()
        self._build_tabs()
        self._build_statusbar()
        self.after(120, self._drain_jobs)
        self.after(150, self.refresh_changes)

    # -- chrome ------------------------------------------------------------
    def _init_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                        font=FONT, borderwidth=0)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("H1.TLabel", background=BG, foreground=FG, font=FONT_H1)
        style.configure("H2.TLabel", background=BG, foreground=FG, font=FONT_BOLD)
        style.configure("Warn.TLabel", background=BG, foreground=WARN)
        style.configure("Err.TLabel", background=BG, foreground=ERR)
        style.configure("Ok.TLabel", background=BG, foreground=OK)
        style.configure("TButton", background="#2a2a35", foreground=FG, padding=(12, 6))
        style.map("TButton", background=[("active", "#3a3a48"), ("disabled", "#20202a")],
                  foreground=[("disabled", "#6a6a75")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#0a84e8"), ("disabled", "#204a6b")],
                  foreground=[("disabled", "#9ab6cc")])
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG,
                        padding=6)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=FG, arrowcolor=FG, padding=4)
        style.map("TCombobox",
                  fieldbackground=[("readonly", PANEL), ("disabled", PANEL)],
                  foreground=[("readonly", FG), ("disabled", "#6a6a75")],
                  background=[("readonly", PANEL)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        padding=(16, 8))
        style.map("TNotebook.Tab", background=[("selected", BG)],
                  foreground=[("selected", FG)])
        style.configure("TSeparator", background=PANEL)

    def _build_header(self):
        header = ttk.Frame(self, padding=(18, 14, 18, 8))
        header.pack(fill="x")
        ttk.Label(header, text="WYSIWYG Patch Tool", style="H1.TLabel").pack(side="left")
        ttk.Label(header, text="  build a small update without reinstalling",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0), pady=(6, 0))

    def _build_statusbar(self):
        bar = ttk.Frame(self, padding=(18, 4, 18, 10))
        bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        self.tab_build = ttk.Frame(self.notebook, padding=16)
        self.tab_apply = ttk.Frame(self.notebook, padding=16)
        self.tab_full = ttk.Frame(self.notebook, padding=16)
        self.tab_help = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(self.tab_build, text="Build a patch")
        self.notebook.add(self.tab_apply, text="Apply a patch")
        self.notebook.add(self.tab_full, text="Full installer")
        self.notebook.add(self.tab_help, text="What can I patch?")

        self._build_build_tab()
        self._build_apply_tab()
        self._build_full_tab()
        self._build_help_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # -- build tab ---------------------------------------------------------
    def _build_build_tab(self):
        root = self.tab_build

        top = ttk.Frame(root)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Current version:", style="Muted.TLabel").pack(side="left")
        self.version_label = ttk.Label(top, text="-", style="H2.TLabel")
        self.version_label.pack(side="left", padx=(8, 0))
        self.bump_button = ttk.Button(top, text="Bump patch version...",
                                      command=self.on_bump)
        self.bump_button.pack(side="right")
        self.build_bump_button = ttk.Button(top, text="Bump build (hotfix)",
                                            command=self.on_bump_build)
        self.build_bump_button.pack(side="right", padx=(0, 6))

        note_row = ttk.Frame(root)
        note_row.pack(fill="x", pady=(0, 10))
        note_label = ttk.Frame(note_row)
        note_label.pack(side="left", anchor="n", pady=(4, 0))
        ttk.Label(note_label, text="What changed:", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(note_label, text="one line per change", style="Muted.TLabel").pack(anchor="w")
        self.note_box = tk.Text(note_row, height=4, wrap="word", bg=PANEL, fg=FG,
                                insertbackground=FG, relief="flat", font=FONT,
                                padx=8, pady=6, highlightthickness=1,
                                highlightbackground=PANEL, highlightcolor=ACCENT)
        self.note_box.pack(side="left", fill="x", expand=True, padx=(10, 0))

        files_head = ttk.Frame(root)
        files_head.pack(fill="x")
        ttk.Label(files_head, text="Changed files", style="H2.TLabel").pack(side="left")
        self.refresh_button = ttk.Button(files_head, text="Refresh", width=9,
                                         command=self.refresh_changes)
        self.refresh_button.pack(side="right")
        self.none_button = ttk.Button(files_head, text="Select none", width=12,
                                      command=lambda: self._check_all(False))
        self.none_button.pack(side="right", padx=(0, 6))
        self.all_button = ttk.Button(files_head, text="Select all", width=11,
                                     command=lambda: self._check_all(True))
        self.all_button.pack(side="right", padx=(0, 6))

        self.files_scroll = ScrollFrame(root, height=200)
        self.files_scroll.pack(fill="both", expand=True, pady=(8, 4))

        self.empty_label = ttk.Label(root, text="No patchable changes found.",
                                     style="Muted.TLabel")
        self.empty_label.pack(anchor="w")

        self.blocked_label = ttk.Label(root, text="", style="Warn.TLabel",
                                       wraplength=920, justify="left")
        self.blocked_label.pack(fill="x", pady=(2, 6))

        add_row = ttk.Frame(root)
        add_row.pack(fill="x", pady=(0, 8))
        self.add_button = ttk.Button(add_row, text="Add file...", command=self.on_add_file)
        self.add_button.pack(side="left")
        ttk.Label(add_row, text="  only loose app files can be patched - see the last tab",
                  style="Muted.TLabel").pack(side="left")

        publish_row = ttk.Frame(root)
        publish_row.pack(fill="x", pady=(0, 8))
        self.publish_var = tk.BooleanVar(value=True)
        self.publish_check = ttk.Checkbutton(
            publish_row, text="Publish to the share after building",
            variable=self.publish_var, command=self._sync_share_state)
        self.publish_check.pack(side="left")
        ttk.Label(publish_row, text="  share:", style="Muted.TLabel").pack(side="left")
        self.share_var = tk.StringVar(value=DEFAULT_SHARE)
        self.share_entry = ttk.Entry(publish_row, textvariable=self.share_var)
        self.share_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._sync_share_state()

        action_row = ttk.Frame(root)
        action_row.pack(fill="x", pady=(4, 8))
        self.build_button = ttk.Button(action_row, text="Build patch", style="Accent.TButton",
                                       command=self.on_build)
        self.build_button.pack(side="left")
        self.build_publish_button = ttk.Button(action_row, text="Build + publish",
                                               command=lambda: self.on_build(publish=True))
        self.build_publish_button.pack(side="left", padx=(8, 0))
        self.open_out_button = ttk.Button(action_row, text="Open output folder",
                                          command=self.on_open_output)
        self.open_out_button.pack(side="right")

        ttk.Label(root, text="Output", style="H2.TLabel").pack(anchor="w", pady=(6, 4))
        log_frame, self.build_log = make_log(root, height=9)
        log_frame.pack(fill="both", expand=False)

    # -- apply tab ---------------------------------------------------------
    def _build_apply_tab(self):
        root = self.tab_apply

        pick_row = ttk.Frame(root)
        pick_row.pack(fill="x", pady=(0, 8))
        ttk.Label(pick_row, text="Patch folder:", style="Muted.TLabel").pack(side="left")
        self.patch_var = tk.StringVar()
        self.patch_entry = ttk.Entry(pick_row, textvariable=self.patch_var)
        self.patch_entry.pack(side="left", fill="x", expand=True, padx=(10, 6))
        ttk.Button(pick_row, text="Browse...", command=self.on_pick_patch).pack(side="left")
        ttk.Button(pick_row, text="Load", command=self.load_patch).pack(side="left", padx=(6, 0))

        self.patch_info = ttk.Label(root, text="Choose a patch folder (or pick the newest "
                                               "one below).",
                                    style="Muted.TLabel", justify="left", wraplength=920)
        self.patch_info.pack(fill="x", pady=(0, 8))

        newest_row = ttk.Frame(root)
        newest_row.pack(fill="x", pady=(0, 10))
        ttk.Label(newest_row, text="Local patches:", style="Muted.TLabel").pack(side="left")
        self.patch_combo = ttk.Combobox(newest_row, state="readonly", width=40)
        self.patch_combo.pack(side="left", padx=(10, 6))
        self.patch_combo.bind("<<ComboboxSelected>>", self._on_combo_pick)
        ttk.Button(newest_row, text="Rescan", command=self.scan_patches).pack(side="left")

        install_row = ttk.Frame(root)
        install_row.pack(fill="x", pady=(0, 10))
        ttk.Label(install_row, text="Install folder:", style="Muted.TLabel").pack(side="left")
        self.install_var = tk.StringVar(value=detect_install_dir())
        self.install_entry = ttk.Entry(install_row, textvariable=self.install_var)
        self.install_entry.pack(side="left", fill="x", expand=True, padx=(10, 6))
        ttk.Button(install_row, text="Browse...", command=self.on_pick_install).pack(side="left")

        options_row = ttk.Frame(root)
        options_row.pack(fill="x", pady=(0, 10))
        self.restart_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_row, text="Restart WYSIWYG after applying",
                        variable=self.restart_var).pack(side="left")
        ttk.Label(options_row, text="   Files are copied and checked while the app runs, then it restarts.",
                  style="Muted.TLabel").pack(side="left")

        action_row = ttk.Frame(root)
        action_row.pack(fill="x", pady=(0, 10))
        self.dry_button = ttk.Button(action_row, text="Dry run (check only)",
                                     command=self.on_dry_run)
        self.dry_button.pack(side="left")
        self.apply_button = ttk.Button(action_row, text="Apply patch", style="Accent.TButton",
                                       command=self.on_apply)
        self.apply_button.pack(side="left", padx=(8, 0))
        ttk.Button(action_row, text="Open backup folder",
                   command=self.on_open_backup).pack(side="right")

        ttk.Label(root, text="Output", style="H2.TLabel").pack(anchor="w", pady=(6, 4))
        log_frame, self.apply_log = make_log(root, height=11)
        log_frame.pack(fill="both", expand=True)

    # -- full installer tab ------------------------------------------------
    def _build_full_tab(self):
        root = self.tab_full

        head = ttk.Frame(root)
        head.pack(fill="x", pady=(0, 8))
        ttk.Label(head, text="One installer that already contains every published patch",
                  style="H2.TLabel").pack(side="left")
        self.full_check_button = ttk.Button(head, text="Check now", command=self.check_full)
        self.full_check_button.pack(side="right")

        self.full_info = ttk.Label(root, text="Click Check now.", style="Muted.TLabel",
                                   justify="left", wraplength=920, font=FONT_MONO)
        self.full_info.pack(fill="x", pady=(0, 10))

        opt = ttk.Frame(root)
        opt.pack(fill="x", pady=(0, 8))
        self.full_publish_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Publish the installer to the share after building",
                        variable=self.full_publish_var,
                        command=self._sync_full_share_state).pack(side="left")
        ttk.Label(opt, text="  share:", style="Muted.TLabel").pack(side="left")
        self.full_share_var = tk.StringVar(value=DEFAULT_SHARE)
        self.full_share_entry = ttk.Entry(opt, textvariable=self.full_share_var)
        self.full_share_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(4, 8))
        self.full_build_button = ttk.Button(actions, text="Build full installer",
                                            style="Accent.TButton",
                                            command=self.on_build_full)
        self.full_build_button.pack(side="left")
        self.sync_button = ttk.Button(actions, text="Pull missing patches into this repo",
                                      command=self.on_sync_repo)
        self.sync_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open dist_install",
                   command=self.on_open_dist).pack(side="right")

        ttk.Label(root, text="Log", style="H2.TLabel").pack(anchor="w", pady=(6, 4))
        log_frame, self.full_log = make_log(root, height=12)
        log_frame.pack(fill="both", expand=True)

    def _on_tab_changed(self, _event=None):
        try:
            current = self.notebook.nametowidget(self.notebook.select())
        except Exception:
            return
        if current is self.tab_full and not self.busy:
            self.check_full()

    def _sync_full_share_state(self):
        self.full_share_entry.configure(
            state="normal" if self.full_publish_var.get() else "disabled")

    def check_full(self):
        if self.busy:
            return
        share = self.full_share_var.get().strip() or DEFAULT_SHARE
        try:
            proc = subprocess.run(ps_command(BUILD_FULL_PS1, ["-Check", "-ShareRoot", share]),
                                  cwd=REPO_ROOT, capture_output=True, text=True,
                                  errors="replace", creationflags=CREATE_NO_WINDOW,
                                  timeout=45)
            text = (proc.stdout or "").strip()
            start = text.find("{")
            if proc.returncode != 0 or start < 0:
                raise RuntimeError((proc.stderr or text or "no output").strip())
            data = json.loads(text[start:])
        except Exception as exc:  # noqa: BLE001
            self.full_info.configure(text="Check failed: " + str(exc), style="Err.TLabel")
            return

        self.full_data = data
        missing = ", ".join(data.get("missing") or []) or "none"
        to_apply = ", ".join(data.get("to_apply") or []) or "none"
        info = (
            "Repo (GOD copy):     {repo}\n"
            "Installer on share:  {installer}\n"
            "Newest patch:        {newest}\n"
            "Target version:      {target}\n"
            "\n"
            "Missing from the installer:  {missing}\n"
            "Patches newer than the repo: {to_apply}"
        ).format(
            repo=data.get("repo", "?"),
            installer=data.get("installer") or "(none)",
            newest=data.get("newest_patch") or "(none)",
            target=data.get("target", "?"),
            missing=missing,
            to_apply=to_apply)
        if data.get("build_needed"):
            info += ("\n\nThe share is behind - a build is needed. The installer will carry "
                     + data.get("target", "?") + ".")
            if data.get("shared_with_patch"):
                info += ("\n\nWARNING: " + data.get("target", "?") + " is already a published patch. "
                         "Machines patched to it will NOT be offered this installer, and two different "
                         "builds would share one number. Bump the version first if this build contains "
                         "Python changes.")
        else:
            info += "\n\nThe share is already at the newest version - nothing to build."
        self.full_info.configure(text=info, style="Warn.TLabel" if data.get("shared_with_patch")
                                 else "Muted.TLabel")

    def on_sync_repo(self):
        if self.busy:
            return
        share = self.full_share_var.get().strip() or DEFAULT_SHARE
        if not messagebox.askyesno(
                "Pull patches into the repo",
                "Apply every published patch that is newer than this repo, and set "
                "version.json / the installer version to match?\n\nThe current files are "
                "backed up under patches\\out\\_prebuild."):
            return
        self.start_job("full", ps_command(BUILD_FULL_PS1, ["-SyncOnly", "-ShareRoot", share]),
                       "Repo synced from the share.")

    def on_build_full(self):
        if self.busy:
            return
        data = getattr(self, "full_data", None) or {}
        target = data.get("target") or "the newest version"
        warning = ""
        if data.get("shared_with_patch"):
            warning = ("\n\nWARNING: {} is already a published patch. Machines already patched to it "
                       "will not be offered this installer. Bump the version first if this build "
                       "contains Python changes.".format(target))
        if not messagebox.askyesno(
                "Build full installer",
                "Build a full installer at {0}?\n\nThis runs !build.bat (a few minutes) and then "
                "Inno Setup. Any published patch the repo lacks is applied first, and the "
                "version files are set to {0}.{1}".format(target, warning)):
            return
        share = self.full_share_var.get().strip() or DEFAULT_SHARE
        args = ["-ShareRoot", share]
        if self.full_publish_var.get():
            args.append("-Publish")
        self.start_job("full", ps_command(BUILD_FULL_PS1, args),
                       "Full installer built at {}. Publishing was {}.".format(
                           target, "requested" if self.full_publish_var.get() else "skipped"))

    def on_open_dist(self):
        dist = os.path.join(REPO_ROOT, "dist_install")
        if os.path.isdir(dist):
            os.startfile(dist)  # noqa: S606 - local folder
        else:
            messagebox.showinfo("Full installer", "dist_install does not exist yet.")

    # -- help tab ----------------------------------------------------------
    def _build_help_tab(self):
        frame = ttk.Frame(self.tab_help)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, bg=LOG_BG, fg=FG, relief="flat", font=FONT,
                       wrap="word", padx=16, pady=12, state="disabled")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        text.tag_configure("h", font=("Segoe UI", 11, "bold"), foreground="#ffffff",
                           spacing1=8, spacing3=4)
        text.tag_configure("code", font=FONT_MONO, foreground="#8ecae6")

        def add(line, tag=None):
            text.configure(state="normal")
            text.insert("end", line + "\n", tag or ())
            text.configure(state="disabled")

        add("What a patch is", "h")
        add("A patch replaces a few files in C:\\FYRTOOLS\\WYSIWYG. The app reads those files "
            "from its own folder before the copies bundled inside the exe, so no rebuild and "
            "no reinstall is needed. A patch is a few hundred KB and applies in seconds.")
        add("")
        add("Files a patch can carry", "h")
        add("app.js, index.html, editor.html, admin.html, search.html, style_guide.html, "
            "styles.css, data.json, media_formats.json, colourmap.json, colourrules.json, "
            "version.json, changelog.txt, the logo files, and ChromeExt\\*.")
        add("")
        add("Never patched", "h")
        add("- Conditions.json: every machine keeps its own favourites and edits.")
        add("- .env / keys.txt: secrets.")
        add("- Anything Python or bundled: main.py, WysiScan, Uberpaste, WysiChat, Adds. "
            "Those need the full installer (!build.bat).")
        add("")
        add("The one rule", "h")
        add("If a batch of changes includes Python, do the full build and skip the patch. "
            "Never publish a full installer under a version that clients already patched to, "
            "or the Python part will never reach them.")
        add("")
        add("Typical run", "h")
        add("1. Type what changed.")
        add("2. Bump the patch version (one click - it updates version.json, the installer "
            "version and the changelog heading).")
        add("3. Untick anything that should not ship.")
        add("4. Build patch, or Build + publish.")
        add("5. Published patches appear in every client's title bar on the next refresh. "
            "One click closes the app, copies, verifies and restarts - nobody has to run "
            "anything by hand.")
        add("6. On a client manually: apply_patch.bat from the share, or the Apply tab here.")
        add("")
        add("What apply does", "h")
        add("Finds the install folder, refuses a patch that is not newer, backs the replaced files "
            "up to C:\\FYRTOOLS\\wysiwyg.patch-backup, copies while the app is still running, "
            "verifies every SHA-256 and rolls back on any mismatch. If the app is running it is left "
            "alone - it serves the new files on the next reload, so no second tab opens. From the "
            "update banner, the page shows a live Patching screen and reloads itself on the new "
            "version.")
        add("")
        add("Full installer", "h")
        add("The Full installer tab builds one INSTALL_WYSIWYG.exe that already contains every "
            "published patch. It reads the repo version, the installer on the share and every "
            "patch, takes the highest as the target, applies any patch the repo is missing, sets "
            "version.json and the installer version to the target, runs !build.bat and then Inno "
            "Setup. Publishing the installer to the share is on by default.")
        add("")
        add("The GOD rule", "h")
        add("C:\\Git\\WysiWyg-Browser is the master copy and must stay the newest. A patch build "
            "refuses to run while a newer patch exists on the share - use 'Pull missing patches "
            "into this repo' (Full installer tab) first. Patch builds publish to the share by "
            "default, so the server never lags behind this checkout.")
        add("")
        add("Same thing from a command prompt", "h")
        add(r"patches\make_patch.bat -Note ""fixed X"" -Changed", "code")
        add(r"patches\make_patch.bat -Note ""fixed X"" -Changed -Publish", "code")
        add(r"patches\apply_patch.bat -DryRun", "code")
        add("")
        add("Full notes: patches\\README.md", "code")

    # -- jobs --------------------------------------------------------------
    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.build_button, self.build_publish_button, self.refresh_button,
                       self.none_button, self.all_button, self.add_button, self.bump_button,
                       self.dry_button, self.apply_button, self.full_build_button,
                       self.sync_button, self.full_check_button, self.build_bump_button):
            try:
                button.configure(state=state)
            except tk.TclError:
                pass
        self.status_var.set("Working..." if busy else "Ready")

    def start_job(self, target, command, success_message=None):
        if self.busy:
            return
        log = getattr(self, target + "_log")
        self._log_clear(log)
        self._set_busy(True)
        script = os.path.basename(command[5]) if len(command) > 5 else command[0]
        tail = command[6:] if len(command) > 6 else []
        self._log(log, "> powershell -File {} {}".format(script, " ".join(tail)), "muted")
        worker = threading.Thread(target=self._run_worker, args=(target, command),
                                  daemon=True)
        worker.start()
        self._pending_success = getattr(self, "_pending_success", {})
        self._pending_success[target] = success_message

    def _run_worker(self, target, command):
        try:
            proc = subprocess.Popen(command, cwd=REPO_ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    errors="replace", bufsize=1,
                                    creationflags=CREATE_NO_WINDOW)
            for line in proc.stdout:
                self.jobs.put(("line", target, line.rstrip("\r\n")))
            proc.wait()
            self.jobs.put(("done", target, proc.returncode))
        except Exception as exc:  # noqa: BLE001 - shown in the log
            self.jobs.put(("line", target, "ERROR: " + str(exc)))
            self.jobs.put(("done", target, 1))

    def _drain_jobs(self):
        try:
            while True:
                item = self.jobs.get_nowait()
                kind, target = item[0], item[1]
                log = getattr(self, target + "_log")
                if kind == "line":
                    line = item[2]
                    tag = ""
                    low = line.lower()
                    if low.startswith("error") or "failed" in low or "mismatch" in low:
                        tag = "err"
                    elif "warning" in low or "cannot" in low:
                        tag = "warn"
                    elif "applied" in low or "published" in low or "patch built" in low:
                        tag = "ok"
                    self._log(log, line, tag)
                else:
                    code = item[2]
                    self._set_busy(False)
                    succeeded = code == 0
                    self._log(log, "", None)
                    self._log(log, "Done (exit code {}).".format(code),
                              "ok" if succeeded else "err")
                    self._after_job(target, succeeded)
        except queue.Empty:
            pass
        self.after(120, self._drain_jobs)

    def _after_job(self, target, succeeded):
        message = (getattr(self, "_pending_success", {}) or {}).get(target)
        if not succeeded:
            messagebox.showerror("Patch tool", "That did not finish. See the output above.")
            return
        if target == "build":
            self.refresh_changes()
            self.scan_patches()
            if self.last_build_dir:
                self.patch_var.set(self.last_build_dir)
                self.load_patch()
            if message:
                messagebox.showinfo("Patch built", message)
        elif target == "apply":
            if message:
                messagebox.showinfo("Patch tool", message)
        elif target == "full":
            self.check_full()
            if message:
                messagebox.showinfo("Full installer", message)

    # -- log helpers -------------------------------------------------------
    def _log(self, widget, line, tag=None):
        widget.configure(state="normal")
        widget.insert("end", (line or "") + "\n", (tag,) if tag else ())
        widget.see("end")
        widget.configure(state="disabled")

    def _log_clear(self, widget):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    # -- build tab actions -------------------------------------------------
    def refresh_changes(self):
        try:
            data = list_changes()
        except Exception as exc:  # noqa: BLE001
            self.blocked_label.configure(text="Could not read git changes: " + str(exc),
                                         style="Err.TLabel")
            return
        self.version_label.configure(text=data.get("version", "?"))
        self.files_scroll.clear()
        self.file_vars = {}
        for item in data.get("files", []):
            self._add_file_row(item.get("path", ""), int(item.get("size", 0)))
        self.empty_label.configure(
            text="" if data.get("files") else "No patchable changes found.")
        blocked = data.get("blocked") or []
        if blocked:
            self.blocked_label.configure(
                text="These changed files cannot go in a patch - they need a full build "
                     "(!build.bat):\n  " + ", ".join(blocked), style="Warn.TLabel")
        else:
            self.blocked_label.configure(text="", style="Warn.TLabel")
        self.scan_patches()

    def _add_file_row(self, rel, size):
        var = tk.BooleanVar(value=True)
        label = rel if size <= 0 else "{}   ({:,} bytes)".format(rel, size)
        check = ttk.Checkbutton(self.files_scroll.inner, text=label, variable=var)
        check.pack(anchor="w", padx=4, pady=1)
        self.file_vars[rel] = var

    def _check_all(self, value):
        for var in self.file_vars.values():
            var.set(value)

    def on_add_file(self):
        path = filedialog.askopenfilename(
            title="Add a file to the patch", initialdir=REPO_ROOT,
            filetypes=[("Patchable files", "*.js *.html *.css *.json *.txt *.png *.ico"),
                       ("All files", "*.*")])
        if not path:
            return
        rel = os.path.relpath(path, REPO_ROOT)
        if rel.startswith(".."):
            messagebox.showerror("Patch tool", "That file is outside the repository.")
            return
        rel = rel.replace("/", "\\")
        if rel in self.file_vars:
            return
        self._add_file_row(rel, os.path.getsize(path))

    def _note_text(self):
        return self.note_box.get("1.0", "end").strip()

    def on_build(self, publish=False):
        if self.busy:
            return
        note = self._note_text()
        if not note:
            messagebox.showwarning("Note required",
                                   "Describe the change first - one line per change.")
            self.note_box.focus_set()
            return
        files = [path for path, var in self.file_vars.items() if var.get()]
        if not files:
            messagebox.showwarning("Nothing selected", "Tick at least one file to ship.")
            return
        if self.blocked_label.cget("text"):
            proceed = messagebox.askyesno(
                "Full build needed for some changes",
                "Some changed files cannot be patched and will NOT be in this patch.\n\n"
                "Build it anyway?")
            if not proceed:
                return

        args = ["-Note", note, "-Files", ",".join(files)]
        if publish or self.publish_var.get():
            args += ["-Publish", "-ShareRoot", self.share_var.get().strip() or DEFAULT_SHARE]

        expected = os.path.join(OUT_ROOT, self.version_label.cget("text"))
        self.last_build_dir = expected
        self.start_job("build", ps_command(MAKE_PS1, args),
                       "Patch {} is in {}".format(os.path.basename(expected), expected))

    def on_bump(self):
        self._bump_version("patch")

    def on_bump_build(self):
        self._bump_version("build")

    def _bump_version(self, kind):
        note = self._note_text()
        if not note:
            messagebox.showwarning("Note required",
                                   "Describe the change first - each line becomes a changelog line.")
            self.note_box.focus_set()
            return
        current = read_version()
        new = dict(current)
        if kind == "build":
            new["build"] = int(current.get("build", 0)) + 1
            what = "fourth digit +1 (bug-fix release); patch number unchanged"
        else:
            new["patch"] = int(current.get("patch", 0)) + 1
            new["build"] = 0
            what = "patch number +1; fourth digit back to 0"
        old_s, new_s = version_str(current), version_str(new)
        today = datetime.date.today().isoformat()
        plan = (
            "{0}  ->  {1}\n\n"
            "{2}\n\n"
            "version.json            -> {1}\n"
            "wysiWyg-installer.iss   MyAppVersion -> {1}\n"
            "changelog.txt           new heading \"### v{1} - {3}\", one -- line per note line\n"
        ).format(old_s, new_s, what, today)
        if not messagebox.askyesno("Bump version", plan + "\nApply these three edits?"):
            return
        try:
            with open(VERSION_FILE, "w", encoding="utf-8", newline="") as fh:
                json.dump(new, fh, indent=4)
                fh.write("\n")
            if os.path.exists(ISS_FILE):
                with open(ISS_FILE, encoding="utf-8", newline="") as fh:
                    iss = fh.read()
                iss = re.sub(r'(#define\s+MyAppVersion\s+")[^"]*(")',
                             r"\g<1>{}\g<2>".format(new_s), iss, count=1)
                with open(ISS_FILE, "w", encoding="utf-8", newline="") as fh:
                    fh.write(iss)
            with open(CHANGELOG_FILE, encoding="utf-8", newline="") as fh:
                changelog = fh.read()
            if not changelog.lstrip("\ufeff").lstrip().startswith("### v" + new_s):
                eol = "\r\n" if "\r\n" in changelog else "\n"
                lines = [line.strip() for line in note.splitlines() if line.strip()]
                entry = "### v{} - {}".format(new_s, today) + eol
                for line in lines:
                    entry += "-- " + line + eol
                entry += eol
                with open(CHANGELOG_FILE, "w", encoding="utf-8", newline="") as fh:
                    fh.write(entry + changelog.lstrip("\ufeff"))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Bump failed", str(exc))
            return
        self.status_var.set("Version bumped to " + new_s)
        self.refresh_changes()

    def _sync_share_state(self):
        self.share_entry.configure(state="normal" if self.publish_var.get() else "disabled")

    def on_open_output(self):
        target = self.last_build_dir or OUT_ROOT
        if not os.path.isdir(target):
            target = OUT_ROOT
        if not os.path.isdir(target):
            messagebox.showinfo("Patch tool", "No patches have been built yet.")
            return
        os.startfile(target)  # noqa: S606 - local folder

    # -- apply tab actions -------------------------------------------------
    def scan_patches(self):
        names = []
        if os.path.isdir(OUT_ROOT):
            for name in sorted(os.listdir(OUT_ROOT), reverse=True):
                if os.path.isfile(os.path.join(OUT_ROOT, name, "patch.json")):
                    names.append(name)
        self.patch_combo.configure(values=names)
        if names and not self.patch_var.get():
            self.patch_combo.set(names[0])
            self.patch_var.set(os.path.join(OUT_ROOT, names[0]))
            self.load_patch()

    def _on_combo_pick(self, _event=None):
        name = self.patch_combo.get()
        if name:
            self.patch_var.set(os.path.join(OUT_ROOT, name))
            self.load_patch()

    def on_pick_patch(self):
        folder = filedialog.askdirectory(title="Patch folder (contains patch.json)",
                                         initialdir=OUT_ROOT if os.path.isdir(OUT_ROOT)
                                         else PATCH_DIR)
        if folder:
            self.patch_var.set(folder)
            self.load_patch()

    def load_patch(self):
        folder = self.patch_var.get().strip()
        manifest_path = os.path.join(folder, "patch.json")
        if not folder or not os.path.isfile(manifest_path):
            self.patch_info.configure(
                text="No patch.json in that folder." if folder else
                "Choose a patch folder.", style="Warn.TLabel")
            return
        try:
            with open(manifest_path, encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            self.patch_info.configure(text="Unreadable patch.json: " + str(exc),
                                      style="Err.TLabel")
            return
        files = data.get("files", [])
        info = "Version {}   |   {} file(s)   |   {}\n{}\n{}".format(
            version_str(data.get("version", {})),
            len(files),
            data.get("created", "unknown date"),
            data.get("note", "") or "(no note)",
            ", ".join(os.path.basename(str(f.get("path", ""))) for f in files))
        self.patch_info.configure(text=info, style="Muted.TLabel")

    def on_pick_install(self):
        folder = filedialog.askdirectory(title="WYSIWYG install folder",
                                         initialdir=self.install_var.get())
        if folder:
            self.install_var.set(folder)

    def _require_patch(self):
        folder = self.patch_var.get().strip()
        if not folder or not os.path.isfile(os.path.join(folder, "patch.json")):
            messagebox.showwarning("Patch tool", "Load a patch folder that contains "
                                                 "patch.json first.")
            return None
        return folder

    def on_dry_run(self):
        folder = self._require_patch()
        if not folder or self.busy:
            return
        args = ["-PatchDir", folder, "-InstallDir", self.install_var.get().strip(),
                "-DryRun"]
        self.start_job("apply", ps_command(APPLY_PS1, args),
                       "Dry run finished - nothing was changed.")

    def on_apply(self):
        folder = self._require_patch()
        if not folder or self.busy:
            return
        if not messagebox.askyesno(
                "Apply patch",
                "Apply this patch to:\n{}\n\nWYSIWYG will be closed and restarted, and the "
                "replaced files are backed up.".format(self.install_var.get().strip())):
            return
        args = ["-PatchDir", folder, "-InstallDir", self.install_var.get().strip(), "-Yes"]
        if not self.restart_var.get():
            args.append("-NoStart")
        self.start_job("apply", ps_command(APPLY_PS1, args),
                       "Patch applied.")

    def on_open_backup(self):
        backup = os.path.join(os.path.dirname(self.install_var.get().strip().rstrip("\\")),
                              "wysiwyg.patch-backup")
        if os.path.isdir(backup):
            os.startfile(backup)  # noqa: S606 - local folder
        else:
            messagebox.showinfo("Patch tool", "No backup yet:\n" + backup)


def main():
    try:
        app = PatchTool()
    except Exception as exc:  # noqa: BLE001
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("WYSIWYG Patch Tool", "Could not start:\n" + str(exc))
        raise
    app.mainloop()


if __name__ == "__main__":
    main()
