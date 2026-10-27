"""Change the editor/admin passwords stored in allpass.json (PBKDF2-hashed).

Usage:
    python set_password.py            # interactive menu
    python set_password.py editor     # set only the editor password
    python set_password.py admin      # set only the admin password

Other keys in allpass.json (media_condition, is_oop, ...) are preserved.
"""
import getpass
import hashlib
import json
import os
import secrets
import shutil
import sys

ITERATIONS = 200000
FILE_PATH = None


def resolve_file_path() -> str:
    """Find the real allpass.json: beside the exe/script first, then common installs."""
    global FILE_PATH
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    candidates = [
        os.path.join(here, "allpass.json"),
        os.path.join(os.getcwd(), "allpass.json"),
        r"C:\FYRTOOLS\WYSIWYG\allpass.json",
        r"C:\Git\WysiWyg-Browser\allpass.json",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            FILE_PATH = candidate
            return FILE_PATH
    FILE_PATH = candidates[0]
    return FILE_PATH


def make_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def load_allpass() -> dict:
    if not os.path.exists(FILE_PATH):
        print(f"{FILE_PATH} not found - a new file will be created.")
        return {}

    # utf-8-sig tolerates a Windows BOM written by other editors.
    with open(FILE_PATH, "r", encoding="utf-8-sig") as f:
        raw = f.read()

    if not raw.strip():
        print(f"WARNING: {FILE_PATH} is empty.")
        print("A new password file will be written (the existing file is kept as .bak).")
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print()
        print(f"ERROR: {FILE_PATH} is not valid JSON ({e}).")
        print("The file looks corrupt. Restore it (or its .bak copy) and run this tool again.")
        sys.exit(1)

    return data if isinstance(data, dict) else {}


def save_allpass(data: dict) -> None:
    if os.path.exists(FILE_PATH):
        shutil.copy2(FILE_PATH, FILE_PATH + ".bak")
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {FILE_PATH}")


def change(key: str, data: dict) -> None:
    print(f"\nChanging the '{key}' password.")
    first = getpass.getpass("New password: ")
    if not first:
        print("Password cannot be empty.")
        return
    second = getpass.getpass("Confirm password: ")
    if first != second:
        print("Passwords did not match.")
        return
    data[key] = make_hash(first)
    save_allpass(data)
    print(f"'{key}' password updated.")


def main() -> None:
    resolve_file_path()
    print(f"Using: {FILE_PATH}")
    choice = sys.argv[1].lower() if len(sys.argv) > 1 else None
    if choice not in (None, "editor", "admin"):
        print(__doc__)
        sys.exit(1)

    data = load_allpass()

    if choice:
        change(choice, data)
        return

    while True:
        print("\n=== Password Manager (allpass.json) ===")
        print("  1) Change editor password")
        print("  2) Change admin password")
        print("  3) Show which keys are set")
        print("  q) Quit")
        selection = input("Choice: ").strip().lower()

        if selection == "1":
            change("editor", data)
        elif selection == "2":
            change("admin", data)
        elif selection == "3":
            for key in ("editor", "admin"):
                value = data.get(key)
                kind = "hashed" if isinstance(value, str) and value.startswith("pbkdf2_sha256$") else (
                    "plaintext" if value else "not set")
                print(f"  {key}: {kind}")
        elif selection == "q":
            break


if __name__ == "__main__":
    main()
