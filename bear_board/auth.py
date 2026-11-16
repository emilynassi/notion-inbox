"""Password login for the Bear Board.

The password is set from the terminal (`server.py --set-password`) and stored
only as a salted scrypt hash in ~/.config/bear-board/config.json (mode 600).
Sessions are signed cookies (HMAC over an expiry time), so they survive server
restarts. Setting a new password rotates the signing secret, which signs out
every device.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("BEAR_BOARD_CONFIG_DIR", Path.home() / ".config" / "bear-board"))
CONFIG_FILE = CONFIG_DIR / "config.json"
COOKIE = "bear_board_session"
SESSION_SECONDS = 30 * 24 * 3600

# Throttle guessing: every failure costs a second, and after 10 failures in
# 10 minutes all logins pause until the window clears. Behind Tailscale every
# request comes from 127.0.0.1, so this is global rather than per-address.
MAX_FAILURES = 10
FAILURE_WINDOW = 600
_failures: list[float] = []
_lock = threading.Lock()


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1).hex()


def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except FileNotFoundError:
        return {}
    return cfg if {"salt", "password_hash", "secret"} <= cfg.keys() else {}


def set_password_interactive() -> None:
    pw = getpass.getpass("New Bear Board password (8+ characters): ")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if getpass.getpass("Type it again: ") != pw:
        raise SystemExit("Passwords didn't match.")
    salt = secrets.token_hex(16)
    cfg = {"salt": salt, "password_hash": _hash(pw, salt), "secret": secrets.token_hex(32)}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f)
    os.chmod(CONFIG_FILE, 0o600)
    print(f"Saved to {CONFIG_FILE}. Restart the board, then sign in. Other devices are signed out.")


def check_password(cfg: dict, password: str) -> tuple[bool, str]:
    """Returns (ok, message). Applies the failure throttle."""
    with _lock:
        now = time.time()
        _failures[:] = [t for t in _failures if now - t < FAILURE_WINDOW]
        if len(_failures) >= MAX_FAILURES:
            return False, "Too many attempts. Try again in a few minutes."
    ok = hmac.compare_digest(_hash(password, cfg["salt"]), cfg["password_hash"])
    if not ok:
        with _lock:
            _failures.append(time.time())
        time.sleep(1)
        return False, "Wrong password."
    return True, ""


def new_session(cfg: dict) -> str:
    expires = str(int(time.time()) + SESSION_SECONDS)
    sig = hmac.new(bytes.fromhex(cfg["secret"]), expires.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def session_valid(cfg: dict, cookie_header: str | None) -> bool:
    if not cfg or not cookie_header:
        return False
    try:
        morsel = SimpleCookie(cookie_header).get(COOKIE)
    except Exception:
        return False
    if not morsel:
        return False
    expires, _, sig = morsel.value.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return False
    good = hmac.new(bytes.fromhex(cfg["secret"]), expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good)


def session_cookie(value: str, secure: bool, max_age: int = SESSION_SECONDS) -> str:
    parts = [f"{COOKIE}={value}", "Path=/", "HttpOnly", "SameSite=Strict", f"Max-Age={max_age}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
