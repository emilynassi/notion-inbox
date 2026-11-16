import { agentAuthorized, json, newSessionSecret } from "@/app/lib/boardAuth";
import { KEYS, store } from "@/app/lib/store";

export const dynamic = "force-dynamic";

// Set by the Mac's setup with a new password. Rotates the session secret: every device signs out.
export async function PUT(req: Request) {
  if (!agentAuthorized(req)) return json({ error: "Unauthorized" }, 401);
  const { kdfSalt, iterations, authVerifier } = await req.json().catch(() => ({}));
  if (!/^[0-9a-f]{32}$/.test(kdfSalt) || !/^[0-9a-f]{64}$/.test(authVerifier)
      || !Number.isInteger(iterations) || iterations < 100_000) {
    return json({ error: "Bad config." }, 400);
  }
  await store().write(KEYS.config, JSON.stringify({ kdfSalt, iterations, authVerifier, sessionSecret: newSessionSecret() }));
  return json({ ok: true });
}
