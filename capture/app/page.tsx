"use client";

import { useEffect, useMemo, useState } from "react";
import { bearCreateUrl, parseCapture } from "@/app/bear";

const DRAFT_KEY = "capture-draft";

function load(key: string): string {
  try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
}
function save(key: string, value: string) {
  try { value ? localStorage.setItem(key, value) : localStorage.removeItem(key); } catch {}
}

export default function CapturePage() {
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("saved")) {
      // Bear sent us back after creating the note.
      save(DRAFT_KEY, "");
      setSaved(true);
      window.history.replaceState(null, "", "/");
    } else {
      // Restore a draft if the hand-off to Bear didn't happen.
      const draft = load(DRAFT_KEY);
      if (draft) {
        try { const d = JSON.parse(draft); setContent(d.content ?? ""); setUrl(d.url ?? ""); } catch {}
      }
    }
  }, []);

  const parsed = useMemo(() => parseCapture(content, url), [content, url]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    save(DRAFT_KEY, JSON.stringify({ content, url }));
    window.location.href = bearCreateUrl(parsed, `${window.location.origin}/?saved=1`);
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-white text-stone-900 dark:bg-black dark:text-stone-100 font-mono">
      <div className="w-full max-w-md flex flex-col gap-6 px-4">
        <h1 className="font-serif text-3xl font-bold tracking-tight">Capture</h1>

        {saved ? (
          <div className="flex flex-col gap-4">
            <p className="text-green-700 dark:text-green-400 font-semibold">Saved to Bear ✓</p>
            <button
              onClick={() => { setSaved(false); setContent(""); setUrl(""); }}
              className="text-stone-500 text-sm underline text-left"
            >
              Add another
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-4">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"What's on your mind?\n#tags work, like #travel/japan"}
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
            {parsed.allTags.length > 0 && (
              <div className="flex flex-wrap gap-2" aria-label="Tags">
                {parsed.allTags.map((t) => (
                  <span key={t} className="rounded-md bg-orange-100 px-2 py-0.5 text-xs uppercase text-orange-700 dark:bg-orange-950 dark:text-orange-300">
                    #{t}
                  </span>
                ))}
              </div>
            )}
            <button
              type="submit"
              disabled={!content.trim()}
              className="rounded-xl bg-stone-900 px-4 py-3 font-semibold text-white hover:bg-stone-700 disabled:opacity-40 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
            >
              Save to Bear
            </button>
            <p className="text-xs text-stone-500">Opens Bear on this device to save the note, then comes back here.</p>
          </form>
        )}
      </div>
    </main>
  );
}
