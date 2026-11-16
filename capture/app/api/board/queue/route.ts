import { randomBytes } from "node:crypto";
import { fromBoard, json, sessionConfig } from "@/app/lib/boardAuth";
import { isEnvelope, MAX_EDIT, MAX_QUEUE, type Queue } from "@/app/lib/envelope";
import { KEYS, readJSON, updateJSON } from "@/app/lib/store";

export const dynamic = "force-dynamic";

// Edits made while the Mac is away. Encrypted in the browser; applied by the Mac agent.
export async function GET(req: Request) {
  if (!(await sessionConfig(req))) return json({ error: "Signed out." }, 401);
  return json((await readJSON<Queue>(KEYS.queue))?.value ?? { edits: [] });
}

export async function POST(req: Request) {
  if (!fromBoard(req)) return json({ error: "forbidden" }, 403);
  if (!(await sessionConfig(req))) return json({ error: "Signed out." }, 401);
  const { envelope } = await req.json().catch(() => ({}));
  if (!isEnvelope(envelope, MAX_EDIT)) return json({ error: "Bad edit." }, 400);
  const id = `${Date.now()}-${randomBytes(6).toString("hex")}`;
  try {
    await updateJSON<Queue>(KEYS.queue, { edits: [] }, (q) => {
      if (q.edits.length >= MAX_QUEUE) throw new Error("Too many changes are waiting for your Mac. Wake it to sync.");
      return { edits: [...q.edits, { id, at: new Date().toISOString(), envelope }] };
    });
  } catch (e) {
    return json({ error: (e as Error).message }, 503);
  }
  return json({ ok: true, id });
}
