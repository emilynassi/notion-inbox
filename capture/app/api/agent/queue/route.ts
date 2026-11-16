import { agentAuthorized, json } from "@/app/lib/boardAuth";
import type { Queue } from "@/app/lib/envelope";
import { KEYS, readJSON, updateJSON } from "@/app/lib/store";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  if (!agentAuthorized(req)) return json({ error: "Unauthorized" }, 401);
  return json((await readJSON<Queue>(KEYS.queue))?.value ?? { edits: [] });
}

// The agent acknowledges edits it has applied; they leave the queue.
export async function POST(req: Request) {
  if (!agentAuthorized(req)) return json({ error: "Unauthorized" }, 401);
  const { ack } = await req.json().catch(() => ({}));
  if (!Array.isArray(ack) || !ack.every((x) => typeof x === "string")) return json({ error: "Bad ack." }, 400);
  if (!ack.length) return json({ ok: true, remaining: null });
  const done = new Set(ack);
  const q = await updateJSON<Queue>(KEYS.queue, { edits: [] }, (cur) => ({ edits: cur.edits.filter((e) => !done.has(e.id)) }));
  return json({ ok: true, remaining: q.edits.length });
}
