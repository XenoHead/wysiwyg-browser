#!/usr/bin/env python3
"""Code-only backup for WysiWYG-Browser.

Zips the listed top-level files + the Adds / WysiScan / WalmartSheet
folders (source/code only) into backups/WYSIWYG_backup_YYYY-MM-DD_HHMMSS.zip,
preserving the directory structure. Locked files (e.g. a debug.log held
by a running process) are skipped instead of aborting the whole backup.
"""
import os, zipfile, datetime, fnmatch

REPO = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(REPO, "backups")

TOP_FILES = [
    "index.html", "app.js", "styles.css", "main.py",
    "conditions.json", "data.json", "version.json", "media_formats.json",
    "allpass.json", "discogs_lists.json", "cost_calc.json",
    "walmart_context_cache.json", "requirements.txt",
    "requirements-current.txt", "WYSIWYG.spec", "INSTALL_WYSIWYG.spec",
    "!build.bat", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md",
]
FOLDERS = ["Adds", "WysiScan", "WalmartSheet"]
INCLUDE = ("*.py", "*.spec", "*.html", "*.js", "*.css", "*.json",
           "*.txt", "*.md", "*.bat", "*.csv")


def in_hidden(path):
    for part in path.split(os.sep):
        if part.startswith("."):
            return True
    return False


def wanted(path):
    # relative to repo
    rel = os.path.relpath(path, REPO)
    if in_hidden(rel):
        return False
    if any(seg in ("temp", "__pycache__", ".venv", "dist", "build") for seg in rel.split(os.sep)):
        return False
    return any(fnmatch.fnmatch(os.path.basename(path), pat) for pat in INCLUDE)


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dt = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    zip_path = os.path.join(BACKUP_DIR, f"WYSIWYG_backup_{dt}.zip")

    candidates = []
    for tf in TOP_FILES:
        p = os.path.join(REPO, tf)
        if os.path.isfile(p) and wanted(p):
            candidates.append(p)
    for fld in FOLDERS:
        base = os.path.join(REPO, fld)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            for fn in files:
                fp = os.path.join(root, fn)
                if wanted(fp):
                    candidates.append(fp)

    added = skipped = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in sorted(candidates):
            arcname = os.path.relpath(fp, REPO)
            try:
                z.write(fp, arcname)
                added += 1
            except (PermissionError, OSError):
                skipped += 1
                print(f"  skipped (locked): {arcname}")

    print(f"Done. Backup: {zip_path}")
    print(f"  {added} files added" + (f", {skipped} skipped" if skipped else ""))
    print(f"  size: {os.path.getsize(zip_path)/1024:.0f} KB")


if __name__ == "__main__":
    main()
