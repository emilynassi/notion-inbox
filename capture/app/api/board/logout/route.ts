import { isSecure, json, sessionCookie } from "@/app/lib/boardAuth";

export async function POST(req: Request) {
  return json({ ok: true }, 200, { "Set-Cookie": sessionCookie(null, isSecure(req)) });
}
