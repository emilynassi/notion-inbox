"use client";

import { useEffect, useMemo, useState } from "react";
import { bearAddTodosUrl, bearCreateUrl, parseCapture, todoLines } from "@/app/bear";

const DRAFT_KEY = "capture-draft";
const LISTS_KEY = "capture-lists";   // titles of Bear notes you add todos to, kept on this device only
const TARGET_KEY = "capture-target"; // "" = new note, otherwise one of the list titles

function load(key: string): string {
  try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
}
function save(key: string, value: string) {
  try { value ? localStorage.setItem(key, value) : localStorage.removeItem(key); } catch {}
}

const chip = "rounded-full border px-3 py-1 text-sm font-semibold";
const chipOff = "border-stone-200 text-stone-600 hover:border-stone-400 dark:border-stone-800 dark:text-stone-300";
const chipOn = "border-stone-900 bg-stone-900 text-white dark:border-stone-100 dark:bg-stone-100 dark:text-stone-900";

export default function CapturePage() {
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [lists, setLists] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    let savedLists: string[] = [];
    try { savedLists = JSON.parse(load(LISTS_KEY) || "[]"); } catch {}
    setLists(savedLists);
    const lastTarget = load(TARGET_KEY);
    if (savedLists.includes(lastTarget)) setTarget(lastTarget);

    const params = new URLSearchParams(window.location.search);
    if (params.has("saved")) {
      // Bear sent us back after saving.
      let to = "";
      try { to = JSON.parse(load(DRAFT_KEY) || "{}").target ?? ""; } catch {}
      save(DRAFT_KEY, "");
      setSaved(to ? `Added to ${to} ✓` : "Saved to Bear ✓");
      window.history.replaceState(null, "", "/");
    } else {
      // Restore a draft if the hand-off to Bear didn't happen.
      try {
        const d = JSON.parse(load(DRAFT_KEY) || "{}");
        setContent(d.content ?? ""); setUrl(d.url ?? "");
        if (d.target && savedLists.includes(d.target)) setTarget(d.target);
      } catch {}
    }
  }, []);

  const parsed = useMemo(() => parseCapture(content, url), [content, url]);
  const items = useMemo(() => (target ? todoLines(content, url) : []), [target, content, url]);

  function choose(t: string) {
    setTarget(t);
    save(TARGET_KEY, t);
  }

  function addList() {
    const title = window.prompt("Exact name of the Bear note to add todos to (e.g. Daily/Weekly Todo):")?.trim();
    if (!title) return;
    const next = [...new Set([...lists, title])];
    setLists(next);
    save(LISTS_KEY, JSON.stringify(next));
    choose(title);
  }

  function removeList(title: string) {
    if (!window.confirm(`Remove "${title}" from this list? (The note in Bear isn't touched.)`)) return;
    const next = lists.filter((l) => l !== title);
    setLists(next);
    save(LISTS_KEY, JSON.stringify(next));
    if (target === title) choose("");
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    save(DRAFT_KEY, JSON.stringify({ content, url, target }));
    const back = `${window.location.origin}/?saved=1`;
    window.location.href = target ? bearAddTodosUrl(target, content, url, back) : bearCreateUrl(parsed, back);
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-white text-stone-900 dark:bg-black dark:text-stone-100 font-mono">
      <div className="w-full max-w-md flex flex-col gap-6 px-4">
        <h1 className="font-serif text-3xl font-bold tracking-tight">Capture</h1>

        {saved ? (
          <div className="flex flex-col gap-4">
            <p className="text-green-700 dark:text-green-400 font-semibold">{saved}</p>
            <button
              onClick={() => { setSaved(null); setContent(""); setUrl(""); }}
              className="text-stone-500 text-sm underline text-left"
            >
              Add another
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Where it goes">
              <button type="button" role="radio" aria-checked={!target} onClick={() => choose("")} className={`${chip} ${!target ? chipOn : chipOff}`}>
                New note
              </button>
              {lists.map((l) => (
                <span key={l} className={`${chip} ${target === l ? chipOn : chipOff} flex items-center gap-1 pr-1`}>
                  <button type="button" role="radio" aria-checked={target === l} onClick={() => choose(l)}>{l}</button>
                  <button type="button" onClick={() => removeList(l)} aria-label={`Remove ${l} from this list`} className="px-1 opacity-50 hover:opacity-100">×</button>
                </span>
              ))}
              <button type="button" onClick={addList} className={`${chip} ${chipOff} border-dashed`}>+ list</button>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={target ? `One todo per line, added to ${target}` : "What's on your mind?\n#tags work, like #travel/japan"}
              required
              autoFocus
              rows={5}
              className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-stone-400 resize-none dark:border-stone-800 dark:bg-stone-900"
            />
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="URL (optional)"
              className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-stone-400 dark:border-stone-800 dark:bg-stone-900"
            />
            {!target && parsed.allTags.length > 0 && (
              <div className="flex flex-wrap gap-2" aria-label="Tags">
                {parsed.allTags.map((t) => (
                  <span key={t} className="rounded-md bg-orange-100 px-2 py-0.5 text-xs uppercase text-orange-700 dark:bg-orange-950 dark:text-orange-300">
                    #{t}
                  </span>
                ))}
              </div>
            )}
            {target && items.length > 0 && (
              <ul className="text-sm text-stone-600 dark:text-stone-300" aria-label="Todos to add">
                {items.map((t, i) => <li key={i}>☐ {t.slice(6)}</li>)}
              </ul>
            )}
            <button
              type="submit"
              disabled={!content.trim()}
              className="rounded-xl bg-stone-900 px-4 py-3 font-semibold text-white hover:bg-stone-700 disabled:opacity-40 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
            >
              {target ? `Add ${items.length > 1 ? `${items.length} todos` : "todo"} to ${target}` : "Save to Bear"}
            </button>
            <p className="text-xs text-stone-500">
              {target
                ? "Opens Bear on this device and adds these to the end of that note, then comes back here. The note is found by its exact name."
                : "Opens Bear on this device to save the note, then comes back here."}
            </p>
          </form>
        )}
      </div>
    </main>
  );
}
