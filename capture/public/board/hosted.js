// Hosted mode for the Bear Board (the website version).
//
// The board page was written for the Mac's local server (/api/notes, /api/tags, …).
// Here there's no Bear, so this script stands in for that server:
//   reads  → download the encrypted snapshot your Mac uploaded, decrypt it here
//   writes → encrypt the change here and add it to a queue; your Mac applies
//            queued changes to Bear the next time it's awake
// Changes still in the queue are layered onto the snapshot, so the board shows them right away.
//
// The decryption key is derived from your password in this browser and kept
// only on this device (IndexedDB, non-extractable). The server never sees it.
(() => {
  const realFetch = window.fetch.bind(window);
  const { deriveKeys, seal, open } = window.BoardCrypto;
  const DB = "bear-board", STORE = "keys", KEY_ID = "enc";
  const REFRESH_MS = 60_000; // re-download at most once a minute (Blob quota)

  let encKey = null;
  let cache = null; // { at, snapshot, pending: [{qid, at, edit}] }
  window.BOARD_LOGIN_URL = "/board/";
  window.BOARD_HOSTED = true;
  // What ↻ found. The website can't make the Mac sync; it can only fetch what the Mac last uploaded.
  window.BOARD_REFRESH_MESSAGE = () => {
    if (!cache) return "Checked for updates";
    const synced = cache.snapshot.syncedAt ? `Mac last synced ${ago(cache.snapshot.syncedAt)}` : "Your Mac hasn't synced yet";
    const waiting = cache.pending.length ? ` · ${cache.pending.length} waiting for it` : "";
    return `Up to date · ${synced}${waiting}`;
  };
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("refresh");
    if (btn) { btn.title = "Check for updates from your Mac"; btn.setAttribute("aria-label", btn.title); }
  });

  // ---- key storage ----
  function idb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function keyOp(mode, fn) {
    try {
      const db = await idb();
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const req = fn(tx.objectStore(STORE));
        tx.oncomplete = () => resolve(req.result);
        tx.onerror = () => reject(tx.error);
      });
    } catch { return null; }
  }
  const loadKey = () => keyOp("readonly", (s) => s.get(KEY_ID));
  const saveKey = (k) => keyOp("readwrite", (s) => s.put(k, KEY_ID));
  const clearKey = () => keyOp("readwrite", (s) => s.delete(KEY_ID));

  async function signOut() {
    await clearKey();
    await realFetch("/api/board/logout", { method: "POST" }).catch(() => {});
    location.reload();
  }

  // ---- sign-in screen ----
  function signInScreen(message) {
    return new Promise((resolve) => {
      const wrap = document.createElement("div");
      wrap.className = "signin";
      wrap.innerHTML = `
        <style>
          .signin { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 16px; background: var(--bg); }
          .signin form { width: min(360px, 100%); display: flex; flex-direction: column; gap: 14px; }
          .signin h1 { margin: 0 0 6px; font: 700 32px/1 "Times New Roman", Georgia, serif; letter-spacing: -1.2px; }
          .signin input { font: inherit; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 0 16px; height: 50px; outline: none; }
          .signin button { height: 50px; border-radius: 12px; justify-content: center; background: var(--text); color: var(--bg); border: 0; }
          .signin .msg { margin: 0; font-size: 14px; color: var(--muted); }
          .signin .msg.err { color: #dc2626; }
        </style>
        <form>
          <h1>Bear Board</h1>
          <input type="password" autocomplete="current-password" placeholder="Password" aria-label="Password" required autofocus>
          <p class="msg" role="alert"></p>
          <button type="submit">Sign in</button>
        </form>`;
      document.body.appendChild(wrap);
      const form = wrap.querySelector("form"), input = wrap.querySelector("input"),
            msg = wrap.querySelector(".msg"), btn = wrap.querySelector("button");
      const say = (text, err) => { msg.textContent = text; msg.classList.toggle("err", !!err); };
      if (message) say(message, true);
      input.focus();
      form.onsubmit = async (e) => {
        e.preventDefault();
        btn.disabled = true;
        say("Unlocking…");
        try {
          const cfgRes = await realFetch("/api/board/config");
          const cfg = await cfgRes.json();
          if (!cfgRes.ok) throw new Error(cfg.error);
          const keys = await deriveKeys(input.value, cfg.kdfSalt, cfg.iterations);
          const res = await realFetch("/api/board/login", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Bear-Board": "1" },
            body: JSON.stringify({ authKey: keys.authKeyHex }),
          });
          if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Couldn't sign in.");
          await saveKey(keys.encKey);
          wrap.remove();
          resolve(keys.encKey);
        } catch (err) {
          say(err.message, true);
          btn.disabled = false;
          input.select();
        }
      };
    });
  }

  // Signed in = a session cookie (checked by fetching the queue) and a key on this device.
  window.BOARD_READY = (async () => {
    await new Promise((r) => (document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", r) : r()));
    document.addEventListener("submit", (e) => {
      if (e.target.matches('form[action="/logout"]')) { e.preventDefault(); signOut(); }
    }, true);
    const stored = await loadKey();
    if (stored) {
      const probe = await realFetch("/api/board/queue");
      if (probe.ok) { encKey = stored; return; }
    }
    encKey = await signInScreen();
  })();

  // ---- reading: snapshot + queued changes ----
  async function refresh(force) {
    if (!force && cache && Date.now() - cache.at < REFRESH_MS) return cache;
    const [snapRes, queueRes] = await Promise.all([realFetch("/api/board/snapshot"), realFetch("/api/board/queue")]);
    if (snapRes.status === 401 || queueRes.status === 401) { await clearKey(); location.reload(); return new Promise(() => {}); }
    const snapRecord = snapRes.ok ? await snapRes.json() : null;
    const snapshot = snapRecord
      ? { ...(await open(encKey, "snapshot", snapRecord.envelope)), uploadedAt: snapRecord.updatedAt }
      : { notes: [], previews: {}, editResults: [], syncedAt: null };
    const queue = queueRes.ok ? await queueRes.json() : { edits: [] };
    const pending = [];
    for (const q of queue.edits) {
      try { pending.push({ qid: q.id, at: q.at, edit: await open(encKey, "edit", q.envelope) }); } catch { /* not ours / undecryptable */ }
    }
    cache = { at: Date.now(), snapshot, pending };
    return cache;
  }

  const parents = (t) => t.split("/").slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join("/"));
  const TAG_RE = /(^|\s)#([\p{L}\p{N}_-]+(?:\/[\p{L}\p{N}_-]+)*)/gu;

  // Apply queued (not yet synced) changes to a copy of the snapshot's notes.
  function withPending({ snapshot, pending }) {
    const notes = new Map(snapshot.notes.map((n) => [n.id, structuredClone(n)]));
    const removed = new Map();
    const touch = (n) => n && (n.syncing = true);
    for (const { qid, at, edit } of pending) {
      const n = notes.get(edit.id);
      if (edit.type === "tags" && n) {
        const add = edit.add || [], remove = edit.remove || [];
        n.tags = [...new Set([...n.tags.filter((t) => !remove.includes(t)), ...add.flatMap(parents), ...add])];
        touch(n);
      } else if (edit.type === "todo" && n) {
        const t = n.openTodos.find((x) => x.i === edit.i);
        if (t) { t.checked = !!edit.done; touch(n); }
      } else if (edit.type === "note") {
        if (edit.action === "restore" && removed.has(edit.id)) notes.set(edit.id, removed.get(edit.id));
        else if (n && edit.action !== "restore") { notes.delete(edit.id); removed.set(edit.id, n); }
      } else if (edit.type === "create") {
        const lines = (edit.content || "").trim().split("\n");
        const title = lines[0].replace(TAG_RE, "$1").replace(/\s+/g, " ").trim() || "Untitled";
        // Checkboxes are numbered the same way the Mac numbers them, so they can be checked off before it syncs.
        const boxes = lines.slice(1).map((l) => l.match(/^\s*[-*]\s+\[( |x|X)\]\s+(.*)$/)).filter(Boolean);
        const openTodos = boxes.map((m, i) => ({ i, text: m[2].trim(), open: m[1] === " " })).filter((t) => t.open);
        notes.set(`pending-${qid}`, {
          id: `pending-${qid}`, title, tags: [...new Set([...(edit.content || "").matchAll(TAG_RE)].map((m) => m[2]))],
          created: at, modified: at, pinned: false, locked: false,
          todos: openTodos.length, done: boxes.length - openTodos.length, openTodos,
          snippet: lines.slice(1).filter((l) => !/^\s*[-*]\s+\[/.test(l)).join("\n").trim().slice(0, 500),
          urls: edit.url ? [edit.url] : [], text: edit.content, syncing: true,
        });
      }
    }
    // A queued #hidden tag hides the note right away, before the Mac syncs (the Mac never uploads hidden notes).
    const hidden = (tags) => tags.some((t) => t.toLowerCase() === "hidden" || t.toLowerCase().startsWith("hidden/"));
    const list = [...notes.values()].filter((n) => !hidden(n.tags));
    const newFirst = (a, b) => (b.pinned - a.pinned) || String(b.modified).localeCompare(String(a.modified));
    return list.sort(newFirst);
  }

  // ---- sync status line ----
  function ago(iso) {
    if (!iso) return "never";
    const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 90) return "just now";
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} d ago`;
  }
  function showStatus({ snapshot, pending }) {
    let el = document.getElementById("syncStatus");
    if (!el) {
      el = Object.assign(document.createElement("div"), { id: "syncStatus", className: "sync-status" });
      document.querySelector(".tools")?.appendChild(el);
    }
    const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const failed = (snapshot.editResults || []).filter((r) => !r.ok && Date.now() - new Date(r.at) < 86400_000);
    el.innerHTML = [
      `<span>Synced from your Mac ${ago(snapshot.syncedAt)}</span>`,
      pending.length ? `<span>⏳ ${pending.length} change${pending.length === 1 ? "" : "s"} waiting for your Mac</span>` : "",
      ...failed.map((r) => `<span class="warn">⚠ Couldn't apply a change: ${esc(r.error)}</span>`),
    ].join("");
  }

  // ---- writing: encrypt and queue ----
  async function enqueue(type, body) {
    const edit = { type, ...body };
    const res = await realFetch("/api/board/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Bear-Board": "1" },
      body: JSON.stringify({ envelope: await seal(encKey, "edit", edit) }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) { await clearKey(); location.reload(); }
    if (!res.ok) return jsonResponse({ error: data.error || "Couldn't save the change." }, res.status);
    cache?.pending.push({ qid: data.id, at: new Date().toISOString(), edit });
    return jsonResponse({ ok: true, id: type === "create" ? `pending-${data.id}` : undefined });
  }

  const jsonResponse = (body, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  const ROUTES = { "/api/tags": "tags", "/api/todo": "todo", "/api/note": "note", "/api/create": "create" };

  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/") || url.pathname.startsWith("/api/board/")) {
      return realFetch(input, init);
    }
    await window.BOARD_READY;
    try {
      if (url.pathname === "/api/notes") {
        // ↻ asks for fresh data; still at most every 10 s, to protect the storage quota.
        const fresh = url.searchParams.has("fresh") && (!cache || Date.now() - cache.at > 10_000);
        const data = await refresh(fresh);
        showStatus(data);
        return jsonResponse(withPending(data));
      }
      if (url.pathname === "/api/preview") {
        const data = await refresh(false);
        return jsonResponse(data.snapshot.previews?.[url.searchParams.get("url")] || {});
      }
      const type = ROUTES[url.pathname];
      if (type && (init.method || "GET").toUpperCase() === "POST") {
        return enqueue(type, JSON.parse(init.body || "{}"));
      }
      return jsonResponse({ error: "Not available on the website." }, 404);
    } catch (err) {
      return jsonResponse({ error: err.message || String(err) }, 500);
    }
  };
})();
