import { json, loadConfig } from "@/app/lib/boardAuth";

export const dynamic = "force-dynamic";

// Public: the browser needs the salt to derive keys before it can sign in.
export async function GET() {
  try {
    const cfg = await loadConfig();
    if (!cfg) return json({ error: "The board isn't set up yet. Run the setup on your Mac." }, 404);
    return json({ kdfSalt: cfg.kdfSalt, iterations: cfg.iterations });
  } catch (e) {
    return json({ error: (e as Error).message }, 503); // e.g. Blob store not connected yet
  }
}
