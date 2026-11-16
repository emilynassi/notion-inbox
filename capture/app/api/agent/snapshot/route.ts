import { agentAuthorized, json } from "@/app/lib/boardAuth";
import { isEnvelope, MAX_SNAPSHOT } from "@/app/lib/envelope";
import { KEYS, store } from "@/app/lib/store";

export const dynamic = "force-dynamic";

export async function PUT(req: Request) {
  if (!agentAuthorized(req)) return json({ error: "Unauthorized" }, 401);
  const { envelope } = await req.json().catch(() => ({}));
  if (!isEnvelope(envelope, MAX_SNAPSHOT)) return json({ error: "Bad snapshot." }, 400);
  await store().write(KEYS.snapshot, JSON.stringify({ updatedAt: new Date().toISOString(), envelope }));
  return json({ ok: true });
}
