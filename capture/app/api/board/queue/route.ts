import { randomBytes } from "node:crypto";
import { fromBoard, json, sessionConfig } from "@/app/lib/boardAuth";
import { isEnvelope, MAX_EDIT, MAX_QUEUE, type Queue, type QueuedEdit } from "@/app/lib/envelope";
import { KEYS, readJSON, updateJSON } from "@/app/lib/store";

export const dynamic = "force-dynamic";

const MAX_BATCH = 50;

// Edits made while the Mac is away. Encrypted in the browser; applied by the Mac agent.
export async function GET(req: Request) {
  if (!(await sessionConfig(req))) return json({ error: "Signed out." }, 401);
  return json((await readJSON<Queue>(KEYS.queue))?.value ?? { edits: [] });
}

// Accepts { envelopes: [...] } (a batch, written in one go) or { envelope } (one).
export async function POST(req: Request) {
  if (!fromBoard(req)) return json({ error: "forbidden" }, 403);
  if (!(await sessionConfig(req))) return json({ error: "Signed out." }, 401);
  const body = await req.json().catch(() => ({}));
  const envelopes: unknown[] = Array.isArray(body.envelopes) ? body.envelopes : body.envelope ? [body.envelope] : [];
  if (!envelopes.length || envelopes.length > MAX_BATCH || !envelopes.every((e) => isEnvelope(e, MAX_EDIT))) {
    return json({ error: "Bad edit." }, 400);
  }
  const at = new Date().toISOString();
  // Ids sort in arrival order, so the Mac applies a batch in the order it was made.
  const items: QueuedEdit[] = envelopes.map((envelope, n) => ({
    id: `${Date.now()}-${String(n).padStart(3, "0")}-${randomBytes(5).toString("hex")}`,
    at,
    envelope: envelope as QueuedEdit["envelope"],
  }));
  try {
    await updateJSON<Queue>(KEYS.queue, { edits: [] }, (q) => {
      if (q.edits.length + items.length > MAX_QUEUE) throw new Error("Too many changes are waiting for your Mac. Wake it to sync.");
      return { edits: [...q.edits, ...items] };
    });
  } catch (e) {
    return json({ error: (e as Error).message }, 503);
  }
  return json({ ok: true, ids: items.map((i) => i.id), id: items[0].id });
}
