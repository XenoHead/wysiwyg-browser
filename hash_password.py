"""Generate hashed password values for allpass.json.

Usage:
    python hash_password.py <password>

Paste the printed value into allpass.json, e.g.:

{
    "editor": "pbkdf2_sha256$200000$<salt>$<hash>",
    "admin": "pbkdf2_sha256$200000$<salt>$<hash>"
}

Plaintext values still work (legacy), but hashed values keep the file safe.
"""
import hashlib
import secrets
import sys

ITERATIONS = 200000


def make_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    print(make_hash(sys.argv[1]))
