"""Card board for Bear notes.

Runs a tiny web server on 127.0.0.1 that reads and edits notes through Bear's
`bearcli`. Every page needs a password login (see auth.py). Other devices can
reach it through Tailscale (see install.sh).

    python3 bear_board/server.py --set-password   # once
    python3 bear_board/server.py                  # http://127.0.0.1:8787
    BEAR_BOARD_PORT=9000 python3 bear_board/server.py
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

BEARCLI = os.environ.get("BEARCLI", "/Applications/Bear.app/Contents/MacOS/bearcli")
HOST = "127.0.0.1"  # never expose notes beyond this machine
PORT = int(os.environ.get("BEAR_BOARD_PORT", "8787"))
# The board page is shared with the hosted website; the local server drops its hosted-only scripts.
INDEX = Path(__file__).resolve().parent.parent / "capture" / "public" / "board" / "index.html"
HOSTED_BLOCK_RE = re.compile(r"<!--HOSTED.*?<!--/HOSTED-->", re.S)
LOGIN = Path(__file__).with_name("login.html")
CFG: dict = {}  # login config, loaded in main()

sys.path.insert(0, str(Path(__file__).parent))
import auth  # noqa: E402

TODO_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")
URL_RE = re.compile(r"https?://[^\s)\]>]+")
HEADING_RE = re.compile(r"^\s*(#+\s+)+|\s+$")  # markdown heading markers, not #tags
IMAGE_RE =re.compile(r"!\[[^\]]*\]\([^)]*\)")
TAG_LINE_RE =re.compile(r"^(\s*#[^\s#][^#]*?#?\s*)+$")


HIDDEN_TAG = "hidden"


def is_hidden(tags: list[str]) -> bool:
    """Notes tagged #hidden (or #hidden/anything) stay off the board, and are never uploaded."""
    return any(t.lower() == HIDDEN_TAG or t.lower().startswith(HIDDEN_TAG + "/") for t in tags)


def load_notes() -> list[dict]:
    out = subprocess.run(
        [BEARCLI, "list", "--format", "json", "--fields", "all,content"],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout
    notes = (shape(n) for n in json.loads(out or "[]"))
    return [n for n in notes if not is_hidden(n["tags"])]


def shape(note: dict) -> dict:
    content = note.get("content") or ""
    lines = content.splitlines()
    title = HEADING_RE.sub("", note.get("title") or "") or "Untitled"
    # Drop the leading "# Title" line Bear stores in the body.
    if lines and HEADING_RE.sub("", lines[0]) == title:
        lines = lines[1:]

    open_todos, body = [], []
    todo_index = 0  # position among all checkbox lines, so the server can find it again
    for line in content.splitlines():
        m = TODO_RE.match(line)
        if m:
            if m.group(1) == " ":
                open_todos.append({"i": todo_index, "text": m.group(2).strip()})
            todo_index += 1
    for line in lines:
        if TODO_RE.match(line):
            continue
        stripped = line.strip()
        if not stripped.strip("#") or TAG_LINE_RE.match(stripped) or IMAGE_RE.fullmatch(stripped):
            continue
        body.append(HEADING_RE.sub("", stripped).replace("**", ""))

    return {
        "id": note["id"],
        "title": title,
        "tags": [t.strip("#") for t in note.get("tags") or []],
        "created": note.get("created"),
        "modified": note.get("modified"),
        "pinned": bool(note.get("pins")),
        "locked": note.get("locked") == "yes",
        "todos": note.get("todos") or 0,
        "done": note.get("done") or 0,
        "openTodos": open_todos,
        "snippet": "\n".join(body[:6])[:500],
        "urls": list(dict.fromkeys(URL_RE.findall(content)))[:3],
        "text": content,  # for client-side search
    }


NOTE_ID_RE = re.compile(r"^[0-9A-Fa-f-]{8,64}$")
# Requests must name one of these hosts. Blocks DNS rebinding, where a web page
# points its own domain at 127.0.0.1 to read the board. Extra names (like the
# Mac's Tailscale address) come from BEAR_BOARD_HOSTS, comma-separated.
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"} | {
    h.strip().lower() for h in os.environ.get("BEAR_BOARD_HOSTS", "").split(",") if h.strip()
}


def clean_tags(tags) -> list[str]:
    if not isinstance(tags, list):
        raise ValueError("tags must be a list")
    out = []
    for t in tags:
        t = str(t).strip().strip("#").strip()
        if not t or t.startswith("-") or len(t) > 100 or "\n" in t:
            raise ValueError(f"bad tag: {t!r}")
        out.append(t)
    return out


def change_tags(note_id: str, add: list, remove: list) -> None:
    if not NOTE_ID_RE.match(note_id):
        raise ValueError("bad note id")
    add, remove = clean_tags(add), clean_tags(remove)
    for verb, tags in (("remove", remove), ("add", add)):
        if tags:
            subprocess.run([BEARCLI, "tags", verb, note_id, *tags],
                           capture_output=True, text=True, timeout=15, check=True)


# Same rules as the capture app (capture/app/bear.ts): tags on the first line
# become the note's tags instead of ending up inside the title heading.
CAPTURE_TAG_RE = re.compile(r"(^|\s)#([\w-]+(?:/[\w-]+)*)")


def create_note(content: str, url: str = "") -> str:
    content, url = str(content).strip(), str(url).strip()
    if not content:
        raise ValueError("Can't save an empty note.")
    if len(content) > 50_000:
        raise ValueError("Note is too long.")
    if url and not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    first, _, body = content.partition("\n")
    tags = [m.group(2) for m in CAPTURE_TAG_RE.finditer(first)]
    title = re.sub(r"\s+", " ", CAPTURE_TAG_RE.sub(r"\1", first)).strip() or "Untitled"
    text = "\n\n".join(p for p in (body.strip(), url) if p)
    # Values are attached with "=" (and the title follows "--") so text starting with "-"
    # is never mistaken for a bearcli option.
    args = [BEARCLI, "create", f"--content={bear_escape(text)}", "--format", "json", "--fields", "id"]
    if tags:
        args += [f"--tags={','.join(tags)}"]
    args += ["--", title]
    out = subprocess.run(args, capture_output=True, text=True, timeout=15, check=True).stdout
    data = json.loads(out)
    return (data[0] if isinstance(data, list) else data)["id"]


def move_note(note_id: str, action: str) -> None:
    """Trash, archive, or restore a note. Trash is Bear's soft delete, never permanent."""
    if not NOTE_ID_RE.match(note_id) or action not in ("trash", "archive", "restore"):
        raise ValueError("bad note action")
    subprocess.run([BEARCLI, action, note_id], capture_output=True, text=True, timeout=15, check=True)


class Conflict(Exception):
    """The note changed since the board loaded it."""


def bear_escape(s: str) -> str:
    # bearcli edit interprets \n, \t, \\ in its arguments; keep text literal.
    return s.replace("\\", "\\\\")


def _read(note_id: str) -> str:
    if not NOTE_ID_RE.match(note_id):
        raise ValueError("bad note id")
    return subprocess.run([BEARCLI, "cat", note_id], capture_output=True, text=True, timeout=15, check=True).stdout


def _replace_line(note_id: str, content: str, li: int, new_text: str | None) -> None:
    """Replace line `li` with `new_text` (which may span lines), or delete it when None.

    The find text grows with neighbouring lines until it's unique in the note, so
    duplicate lines elsewhere are never touched.
    """
    lines = content.split("\n")
    last = len(lines) - 1
    start = end = li

    def span(replacement: str | None = "\0keep") -> str:
        middle = [lines[li]] if replacement == "\0keep" else ([] if replacement is None else [replacement])
        mid = lines[start:li] + middle + lines[li + 1:end + 1]
        text = "\n".join(mid)
        return text + ("\n" if end < last and mid else "")  # trailing \n pins whole lines

    while content.count(span()) > 1 and (start > 0 or end < last):
        start, end = max(start - 1, 0), min(end + 1, last)
    replacement = span(new_text)
    action = [f"--replace={bear_escape(replacement)}"] if replacement else ["--delete"]
    subprocess.run([BEARCLI, "edit", note_id, "--no-update-modified", f"--find={bear_escape(span())}", *action],  # "=" form: text may start with "-"
                   capture_output=True, text=True, timeout=15, check=True)


def _locate_todo(content: str, index, text: str) -> tuple[int, re.Match]:
    """Line number of the index-th checkbox line, checked against the text the board saw."""
    if not isinstance(index, int) or index < 0:
        raise ValueError("bad todo reference")
    lines = content.split("\n")
    todo_lines = [i for i, line in enumerate(lines) if TODO_RE.match(line)]
    if index >= len(todo_lines):
        raise Conflict("That todo isn't in the note anymore. Reload and try again.")
    li = todo_lines[index]
    m = TODO_RE.match(lines[li])
    if m.group(2).strip() != str(text).strip():
        raise Conflict("The note changed in Bear. Reload and try again.")
    return li, m


def set_todo(note_id: str, index, text: str, done: bool) -> None:
    """Check or uncheck the index-th checkbox line in a note."""
    content = _read(note_id)
    li, m = _locate_todo(content, index, text)
    if (m.group(1) != " ") == done:
        return  # already in the requested state
    line = content.split("\n")[li]
    _replace_line(note_id, content, li, line[: m.start(1) - 1] + ("[x]" if done else "[ ]") + line[m.end(1) + 1:])


def clean_todo_text(text) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if not text:
        raise ValueError("Can't add an empty todo.")
    if len(text) > 1_000:
        raise ValueError("That todo is too long.")
    return text


def add_todo(note_id: str, text: str) -> int:
    """Add an open checkbox right after the note's last one (or at the end). Returns its index."""
    text = clean_todo_text(text)
    content = _read(note_id)
    lines = content.split("\n")
    todo_lines = [i for i, line in enumerate(lines) if TODO_RE.match(line)]
    if not todo_lines:
        subprocess.run([BEARCLI, "append", note_id, "--no-update-modified", f"--content={bear_escape(f'- [ ] {text}')}"],
                       capture_output=True, text=True, timeout=15, check=True)
        return 0
    li = todo_lines[-1]
    prefix = re.match(r"^(\s*[-*]\s+)\[", lines[li]).group(1)  # same indent and bullet as the list
    _replace_line(note_id, content, li, f"{lines[li]}\n{prefix}[ ] {text}")
    return len(todo_lines)


def remove_todo(note_id: str, index, text: str) -> None:
    """Delete the index-th checkbox line (used to undo add_todo)."""
    content = _read(note_id)
    li, _ = _locate_todo(content, index, text)
    _replace_line(note_id, content, li, None)


_previews: dict[str, dict] = {}
META_RE = re.compile(r"<meta\s+[^>]*>", re.I)
ATTR_RE = re.compile(r'(property|name|content)\s*=\s*["\']([^"\']*)["\']', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def link_preview(url: str) -> dict:
    """Title + image for a link, read from the page's Open Graph tags. Cached in memory."""
    if not url.startswith(("http://", "https://")):
        return {}
    if url in _previews:
        return _previews[url]
    result = {"url": url}
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (BearBoard link preview)"})
        with urlopen(req, timeout=5) as resp:
            if "html" in resp.headers.get("Content-Type", ""):
                html_text = resp.read(400_000).decode("utf-8", "replace")
                meta = {}
                for tag in META_RE.findall(html_text):
                    attrs = {k.lower(): v for k, v in ATTR_RE.findall(tag)}
                    key = attrs.get("property") or attrs.get("name")
                    if key and "content" in attrs:
                        meta.setdefault(key.lower(), html.unescape(attrs["content"]))
                title = meta.get("og:title") or meta.get("twitter:title")
                if not title and (m := TITLE_RE.search(html_text)):
                    title = html.unescape(m.group(1).strip())
                image = meta.get("og:image") or meta.get("twitter:image")
                result.update(title=title, image=urljoin(url, image) if image else None)
    except (OSError, ValueError):
        pass  # unreachable link: the card just shows the bare URL
    _previews[url] = result
    return result


class Handler(BaseHTTPRequestHandler):
    def _host_ok(self) -> bool:
        if (self.headers.get("Host") or "").lower() in ALLOWED_HOSTS:
            return True
        self._send(403, b"forbidden host", "text/plain")
        return False

    # ---- Login ----
    def _secure(self) -> bool:
        # Anything not addressed to localhost arrives through Tailscale's HTTPS proxy.
        return (self.headers.get("Host") or "").split(":")[0] not in ("127.0.0.1", "localhost")

    def _authed(self) -> bool:
        if auth.session_valid(CFG, self.headers.get("Cookie")):
            return True
        if self.path.startswith("/api/"):
            self._send(401, b'{"error":"Signed out. Reload to sign in."}', "application/json")
        else:
            self._redirect("/login")
        return False

    def _redirect(self, to: str, cookie: str | None = None):
        self.send_response(303)
        self.send_header("Location", to)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _login_page(self, error: str = "", code: int = 200):
        page = LOGIN.read_text().replace("{{error}}", html.escape(error))
        self._send(code, page.encode(), "text/html; charset=utf-8")

    def _login(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(min(length, 4_000)).decode("utf-8", "replace"))
        ok, message = auth.check_password(CFG, form.get("password", [""])[0])
        if not ok:
            return self._login_page(message, 401)
        self._redirect("/", auth.session_cookie(auth.new_session(CFG), self._secure()))

    def do_GET(self):
        if not self._host_ok():
            return
        if self.path == "/login":
            return self._redirect("/") if auth.session_valid(CFG, self.headers.get("Cookie")) else self._login_page()
        if not self._authed():
            return
        if self.path in ("/", "/index.html"):
            page = HOSTED_BLOCK_RE.sub("", INDEX.read_text())
            self._send(200, page.encode(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/preview?"):
            url = parse_qs(urlparse(self.path).query).get("url", [""])[0]
            self._send(200, json.dumps(link_preview(url)).encode(), "application/json")
        elif urlparse(self.path).path == "/api/notes":  # ?fresh=1 is a no-op here: always read live from Bear
            try:
                body = json.dumps(load_notes()).encode()
                self._send(200, body, "application/json")
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        # Only accept writes from the board itself: right Host (blocks DNS
        # rebinding) and a custom header (forces a CORS preflight we never
        # approve, so other websites can't post here).
        if not self._host_ok():
            return
        if self.path == "/login":
            return self._login()
        if self.path == "/logout":
            return self._redirect("/login", auth.session_cookie("", self._secure(), max_age=0))
        if not self._authed():
            return
        if self.headers.get("X-Bear-Board") != "1":
            return self._send(403, b"forbidden", "text/plain")
        if self.path not in ("/api/tags", "/api/todo", "/api/note", "/api/create", "/api/todo/add", "/api/todo/remove"):
            return self._send(404, b"not found", "text/plain")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(min(length, 200_000)) or "{}")
            if self.path == "/api/todo/add":
                i = add_todo(req.get("id", ""), req.get("text", ""))
                return self._send(200, json.dumps({"ok": True, "i": i}).encode(), "application/json")
            if self.path == "/api/todo/remove":
                remove_todo(req.get("id", ""), req.get("i"), req.get("text", ""))
                return self._send(200, b'{"ok":true}', "application/json")
            if self.path == "/api/create":
                note_id = create_note(req.get("content", ""), req.get("url", ""))
                return self._send(200, json.dumps({"ok": True, "id": note_id}).encode(), "application/json")
            if self.path == "/api/tags":
                change_tags(req.get("id", ""), req.get("add") or [], req.get("remove") or [])
            elif self.path == "/api/note":
                move_note(req.get("id", ""), req.get("action", ""))
            else:
                set_todo(req.get("id", ""), req.get("i"), req.get("text", ""), bool(req.get("done")))
            self._send(200, b'{"ok":true}', "application/json")
        except Conflict as e:
            self._send(409, json.dumps({"error": str(e)}).encode(), "application/json")
        except ValueError as e:
            self._send(400, json.dumps({"error": str(e)}).encode(), "application/json")
        except subprocess.CalledProcessError as e:
            self._send(500, json.dumps({"error": (e.stderr or str(e)).strip()}).encode(), "application/json")

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass


def main():
    global CFG
    if "--set-password" in sys.argv[1:]:
        return auth.set_password_interactive()
    if not os.access(BEARCLI, os.X_OK):
        raise SystemExit(f"Can't find Bear's bearcli at {BEARCLI}. Install Bear 2 or set BEARCLI=/path/to/bearcli.")
    CFG = auth.load_config()
    if not CFG:
        raise SystemExit("No board password yet. Set one with:\n  python3 bear_board/server.py --set-password")
    print(f"Bear board on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
