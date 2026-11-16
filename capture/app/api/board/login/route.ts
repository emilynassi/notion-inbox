import { fromBoard, isSecure, json, loadConfig, sessionCookie, verifyAuthKey } from "@/app/lib/boardAuth";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  if (!fromBoard(req)) return json({ error: "forbidden" }, 403);
  const cfg = await loadConfig();
  if (!cfg) return json({ error: "The board isn't set up yet." }, 404);
  const { authKey } = await req.json().catch(() => ({}));
  if (typeof authKey !== "string" || !verifyAuthKey(cfg, authKey)) {
    await new Promise((r) => setTimeout(r, 1000)); // slow down guessing
    return json({ error: "Wrong password." }, 401);
  }
  return json({ ok: true }, 200, { "Set-Cookie": sessionCookie(cfg, isSecure(req)) });
}
