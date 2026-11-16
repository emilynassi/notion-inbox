"""Sync agent for the hosted Bear Board.

Runs on the Mac with Bear (every 10 minutes while it's awake, via launchd):
  1. downloads changes queued on the website, decrypts them, applies them to Bear
  2. uploads an encrypted snapshot of your notes when something changed

    sync_agent.py setup    # once: site URL + password, then follow the prompts
    sync_agent.py run      # one sync pass (what launchd runs)
    sync_agent.py status

Secrets live in ~/.config/bear-board/sync.json (mode 600): the agent token and
the encryption key derived from your password. The password itself is never stored.

Vercel Blob's free tier allows ~2,000 uploads a month, so uploads are rationed:
right after applying your changes, otherwise at most every 30 minutes when notes
changed, plus a heartbeat every 6 hours.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import boardcrypto as bc  # noqa: E402
import server  # noqa: E402  (Bear access: load_notes, change_tags, set_todo, move_note, create_note, link_preview)

DIR = Path(os.environ.get("BEAR_BOARD_CONFIG_DIR", Path.home() / ".config" / "bear-board"))
SECRETS = DIR / "sync.json"
STATE = DIR / "sync-state.json"
UPLOAD_EVERY = int(os.environ.get("BEAR_BOARD_UPLOAD_EVERY", 30 * 60))
HEARTBEAT_EVERY = 6 * 3600
NEW_PREVIEWS_PER_RUN = 15


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def write_private(path: Path, data: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


class Api:
    def __init__(self, site: str, token: str):
        self.site, self.token = site.rstrip("/"), token

    def call(self, method: str, path: str, body=None):
        req = urllib.request.Request(
            self.site + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                     "User-Agent": "bear-board-sync"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            raise RuntimeError(f"{method} {path} → HTTP {e.code}: {detail}") from None


# ---------- setup ----------

def setup() -> None:
    existing = read_json(SECRETS, {})
    site = input(f"Board website URL [{existing.get('site', 'https://your-capture-site.vercel.app')}]: ").strip() or existing.get("site")
    if not site or not site.startswith("https://") and "localhost" not in site and "127.0.0.1" not in site:
        raise SystemExit("Use the https:// address of your Vercel site.")
    pw = getpass.getpass("Board password (8+ characters, used to encrypt your notes): ")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if getpass.getpass("Type it again: ") != pw:
        raise SystemExit("Passwords didn't match.")

    token = existing.get("agentToken") or secrets.token_urlsafe(32)
    kdf_salt = secrets.token_hex(16)
    print("Deriving keys (a few seconds)…")
    auth_key, enc_key = bc.derive_keys(pw, kdf_salt, bc.ITERATIONS)
    write_private(SECRETS, {"site": site.rstrip("/"), "agentToken": token, "encKey": enc_key.hex(),
                            "kdfSalt": kdf_salt, "iterations": bc.ITERATIONS})
    # A new password means a new key: forget what was uploaded under the old one.
    state = read_json(STATE, {})
    state.pop("lastHash", None)
    write_private(STATE, state)

    api = Api(site, token)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    while True:
        try:
            api.call("PUT", "/api/agent/config",
                     {"kdfSalt": kdf_salt, "iterations": bc.ITERATIONS, "authVerifier": bc.auth_verifier(auth_key)})
            break
        except RuntimeError as e:
            if "HTTP 401" not in str(e):
                raise SystemExit(f"Couldn't reach the site: {e}")
            print(f"""
One-time step in Vercel (the site doesn't know this Mac yet):
  1. Open your capture project → Settings → Environment Variables
  2. Add  BOARD_AGENT_TOKEN_SHA256 = {token_hash}
  3. Redeploy the project (Deployments → … → Redeploy)
""")
            input("Press Enter once it has redeployed… ")
    print("✓ Website now knows your password (only a verifier; it can't decrypt).")
    run(force_upload=True)
    print(f"✓ First sync done. Open {site.rstrip('/')}/board and sign in. Other devices are signed out.")


# ---------- one sync pass ----------

def apply_edit(edit: dict, qid: str, state: dict) -> None:
    def real(note_id: str) -> str:
        if note_id.startswith("pending-"):
            mapped = state.setdefault("pendingMap", {}).get(note_id)
            if not mapped:
                raise ValueError("That note was never created.")
            return mapped
        return note_id

    kind = edit.get("type")
    if kind == "tags":
        server.change_tags(real(edit["id"]), edit.get("add") or [], edit.get("remove") or [])
    elif kind == "todo":
        server.set_todo(real(edit["id"]), edit.get("i"), edit.get("text", ""), bool(edit.get("done")))
    elif kind == "addTodo":
        server.add_todo(real(edit["id"]), edit.get("text", ""))
    elif kind == "removeTodo":
        server.remove_todo(real(edit["id"]), edit.get("i"), edit.get("text", ""))
    elif kind == "note":
        server.move_note(real(edit["id"]), edit.get("action", ""))
    elif kind == "create":
        state.setdefault("pendingMap", {})[f"pending-{qid}"] = server.create_note(edit.get("content", ""), edit.get("url", ""))
    else:
        raise ValueError(f"Unknown change type {kind!r}")


def run(force_upload: bool = False) -> None:
    sec = read_json(SECRETS, None)
    if not sec:
        raise SystemExit("Not set up. Run: sync_agent.py setup")
    api, enc_key = Api(sec["site"], sec["agentToken"]), bytes.fromhex(sec["encKey"])
    state = read_json(STATE, {})
    applied: dict = state.setdefault("applied", {})
    results: list = state.setdefault("results", [])

    # 1. Apply queued changes, oldest first. Each is recorded as applied before it's
    #    acknowledged, so a failure partway never applies anything twice.
    queue = api.call("GET", "/api/agent/queue").get("edits", [])
    acks, new_results = [], 0
    for item in sorted(queue, key=lambda e: e["id"]):
        qid = item["id"]
        if qid not in applied:
            result = {"qid": qid, "at": now_iso(), "ok": True}
            try:
                edit = bc.open_(enc_key, "edit", item["envelope"])
                result["type"] = edit.get("type")
                apply_edit(edit, qid, state)
            except Exception as e:  # one bad change shouldn't block the rest
                result.update(ok=False, error=getattr(e, "stderr", None) or str(e))
            applied[qid] = now_iso()
            results.append(result)
            new_results += 1
            write_private(STATE, state)
            log(f"applied {qid}: {'ok' if result['ok'] else result['error']}")
        acks.append(qid)
    if acks:
        api.call("POST", "/api/agent/queue", {"ack": acks})
    # Forget old bookkeeping.
    cutoff = time.time() - 30 * 86400
    state["applied"] = {k: v for k, v in applied.items() if datetime.fromisoformat(v).timestamp() > cutoff}
    state["results"] = results[-30:]

    # 2. Snapshot of Bear, with link previews fetched here (the website never sees your links).
    notes = server.load_notes()
    previews: dict = state.setdefault("previews", {})
    budget = NEW_PREVIEWS_PER_RUN
    for n in notes:
        url = (n.get("urls") or [None])[0]
        if url and url not in previews and budget > 0:
            previews[url] = server.link_preview(url)
            budget -= 1
    wanted = {(n.get("urls") or [None])[0] for n in notes}
    state["previews"] = previews = {u: p for u, p in previews.items() if u in wanted}

    body = {"notes": notes, "previews": previews, "editResults": state["results"]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    since = time.time() - state.get("lastUpload", 0)
    changed = digest != state.get("lastHash")
    if force_upload or new_results or (changed and since >= UPLOAD_EVERY) or since >= HEARTBEAT_EVERY:
        api.call("PUT", "/api/agent/snapshot", {"envelope": bc.seal(enc_key, "snapshot", {**body, "syncedAt": now_iso()})})
        state.update(lastHash=digest, lastUpload=time.time())
        log(f"uploaded snapshot ({len(notes)} notes)")
    write_private(STATE, state)


def status() -> None:
    sec, state = read_json(SECRETS, None), read_json(STATE, {})
    if not sec:
        return print("Not set up. Run: sync_agent.py setup")
    last = state.get("lastUpload")
    print(f"Site:        {sec['site']}/board")
    print(f"Last upload: {datetime.fromtimestamp(last):%Y-%m-%d %H:%M}" if last else "Last upload: never")
    failed = [r for r in state.get("results", []) if not r["ok"]]
    print(f"Recent changes applied: {len(state.get('results', []))}, failed: {len(failed)}")
    for r in failed[-5:]:
        print(f"  ✗ {r['at']} {r.get('type')}: {r['error']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        {"setup": setup, "run": run, "status": status}[cmd]()
    except KeyError:
        raise SystemExit(__doc__)
    except (RuntimeError, OSError) as e:
        log(f"sync failed: {e}")  # offline or site unreachable: try again next time
        sys.exit(1)
