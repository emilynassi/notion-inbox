"use client";

import { useActionState } from "react";
import { capture } from "@/app/actions/capture";

export default function CapturePage() {
  const [state, action, pending] = useActionState(capture, "" as string);
  const submitted = state === "ok";
  const isError = state && !submitted;

  return (
    <main className="min-h-screen flex items-center justify-center bg-stone-50">
      <div className="w-full max-w-sm flex flex-col gap-6 px-4">
        <h1 className="text-xl font-semibold text-stone-800">Add to inbox</h1>

        {submitted ? (
          <div className="flex flex-col gap-4">
            <p className="text-green-700 font-medium">Saved to inbox ✓</p>
            <button
              onClick={() => window.location.reload()}
              className="text-stone-500 text-sm underline text-left"
            >
              Add another
            </button>
          </div>
        ) : (
          <form action={action} className="flex flex-col gap-4">
            <textarea
              name="content"
              placeholder="What's on your mind?"
              required
              autoFocus
              rows={4}
              className="border border-stone-300 rounded-lg px-4 py-2 text-stone-800 focus:outline-none focus:ring-2 focus:ring-stone-400 resize-none"
            />
            <input
              type="url"
              name="url"
              placeholder="URL (optional)"
              className="border border-stone-300 rounded-lg px-4 py-2 text-stone-800 focus:outline-none focus:ring-2 focus:ring-stone-400"
            />
            {isError && <p className="text-red-500 text-sm">{state}</p>}
            <button
              type="submit"
              disabled={pending}
              className="bg-stone-800 text-white rounded-lg px-4 py-2 font-medium hover:bg-stone-700 disabled:opacity-50"
            >
              {pending ? "Saving…" : "Save to inbox"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
