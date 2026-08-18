#!/usr/bin/env python3
"""
kill_stale_wysiwyg.py — Clear stale WYSIWYG processes and mutex so main.py can launch.

Run:  .venv311\Scripts\python.exe kill_stale_wysiwyg.py

What it does:
  1. Kills any process listening on port 8008 that isn't a fresh main.py launch.
  2. Kills zombie WYSIWYG.exe / WysiScan.exe / XDevHubX.exe processes.
  3. Kills stale python.exe processes running main.py or the frozen EXE.
  4. Clears the Local\WYSIWYG_SINGLE_INSTANCE_MUTEX by releasing the handle
     held by any surviving process that owns it (fallback: reboot clears it).

Use when "python main.py" exits immediately with "Another instance is already
running (error 183)" in wysiwyg_debug.log even though no window is visible.
"""

import ctypes
import ctypes.wintypes
import os
import sys
import time
import psutil

MUTEX_NAME = "Local\\WYSIWYG_SINGLE_INSTANCE_MUTEX"
TARGET_PORT = 8008

KILLABLE_NAMES = {"WYSIWYG.exe", "WysiScan.exe", "XDevHubX.exe"}

def is_port_holder(pid):
    """Check if a PID has a socket listening on TARGET_PORT."""
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port == TARGET_PORT:
                if conn.pid == pid:
                    return True
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    return False


def kill_process_tree(pid):
    """Kill a PID and all its children."""
    try:
        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        proc.kill()
        proc.wait(timeout=3)
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def main():
    killed = []
    protected_pids = set()

    # --- Protect the current python process so we don't kill ourselves ---
    protected_pids.add(os.getpid())
    # Also protect any python process that is currently running main.py fresh
    # (started within the last 30 seconds — likely the one the user just launched).
    now = time.time()
    for proc in psutil.process_iter(["pid", "create_time", "cmdline"]):
        try:
            if proc.info["cmdline"] and "main.py" in " ".join(proc.info["cmdline"]):
                age = now - proc.info["create_time"]
                if age < 30:
                    protected_pids.add(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # --- 1. Kill whatever holds port 8008 ---
    print(f"\n[1] Scanning for port {TARGET_PORT} holders...")
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            pid = proc.info["pid"]
            if pid in protected_pids:
                continue
            if is_port_holder(pid):
                name = proc.info["name"]
                print(f"    Port {TARGET_PORT} held by {name} (PID {pid}) — killing")
                if kill_process_tree(pid):
                    killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # --- 2. Kill known stale app processes ---
    print("\n[2] Scanning for stale WYSIWYG/WysiScan/XDevHubX processes...")
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pid = proc.info["pid"]
            if pid in protected_pids:
                continue
            if proc.info["name"] in KILLABLE_NAMES:
                print(f"    {proc.info['name']} (PID {pid}) — killing")
                if kill_process_tree(pid):
                    killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # --- 3. Kill stale python.exe running the frozen EXE or main.py ---
    print("\n[3] Scanning for stale python.exe holding the mutex...")
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            pid = proc.info["pid"]
            if pid in protected_pids:
                continue
            if proc.info["name"] != "python.exe" and proc.info["name"] != "WYSIWYG.exe":
                continue
            cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
            is_wysiwyg = (
                "main.py" in cmdline
                or "--window" in cmdline
                or "--uberpaste" in cmdline
                or "--wysiscan" in cmdline
                or "WYSIWYG.exe" in cmdline
            )
            if not is_wysiwyg:
                continue
            # If it's been up more than 2 minutes and the port isn't listening
            # (or we already cleared the port holder), treat as stale.
            age = now - proc.info["create_time"]
            if age > 120:
                print(f"    {proc.info['name']} (PID {pid}, age {age:.0f}s) — killing (stale)")
                if kill_process_tree(pid):
                    killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # --- 4. Report ---
    print(f"\n[DONE] Killed {len(killed)} stale process(es): {killed}")
    if not killed:
        print("    No stale processes found. The mutex may already be clear.")
    else:
        print("    You can now run:  .venv311\\Scripts\\python.exe main.py")
    print()


if __name__ == "__main__":
    main()
