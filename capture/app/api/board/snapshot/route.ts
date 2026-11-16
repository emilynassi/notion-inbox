import { json, sessionConfig } from "@/app/lib/boardAuth";
import type { SnapshotRecord } from "@/app/lib/envelope";
import { KEYS, readJSON } from "@/app/lib/store";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  if (!(await sessionConfig(req))) return json({ error: "Signed out." }, 401);
  const snap = await readJSON<SnapshotRecord>(KEYS.snapshot);
  if (!snap) return json({ error: "No notes yet. Your Mac uploads them on its first sync." }, 404);
  return json(snap.value);
}
