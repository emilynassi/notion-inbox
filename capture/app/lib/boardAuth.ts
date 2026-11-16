// Sign-in for the hosted board, and authentication for the Mac sync agent.
//
// Browser: derives authKey from the password (PBKDF2 + HKDF, see
// public/board/boardcrypto.js) and sends it here. We store only
// SHA-256(authKey), so the server can check sign-ins but never sees the
// password or the encryption key. A signed session cookie follows.
//
// Agent: sends a random bearer token; its SHA-256 is the
// BOARD_AGENT_TOKEN_SHA256 environment variable set in Vercel.

import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { KEYS, readJSON } from "@/app/lib/store";

export type BoardConfig = {
  kdfSalt: string;
  iterations: number;
  authVerifier: string;
  sessionSecret: string;
};

const COOKIE = "bear_board_hosted";
const SESSION_SECONDS = 30 * 24 * 3600;

const sha256 = (s: string | Buffer) => createHash("sha256").update(s).digest();
function safeEqualHex(aHex: string, bHex: string): boolean {
  const a = Buffer.from(aHex, "hex"), b = Buffer.from(bHex, "hex");
  return a.length === b.length && a.length > 0 && timingSafeEqual(a, b);
}

export const newSessionSecret = () => randomBytes(32).toString("hex");

export async function loadConfig(): Promise<BoardConfig | null> {
  return (await readJSON<BoardConfig>(KEYS.config))?.value ?? null;
}

export function verifyAuthKey(cfg: BoardConfig, authKeyHex: string): boolean {
  if (!/^[0-9a-f]{64}$/.test(authKeyHex)) return false;
  return safeEqualHex(sha256(Buffer.from(authKeyHex, "hex")).toString("hex"), cfg.authVerifier);
}

function sign(cfg: BoardConfig, expires: string) {
  return createHmac("sha256", Buffer.from(cfg.sessionSecret, "hex")).update(expires).digest("hex");
}

export function sessionCookie(cfg: BoardConfig | null, secure: boolean): string {
  const base = `${COOKIE}=`;
  const attrs = ["Path=/", "HttpOnly", "SameSite=Strict", ...(secure ? ["Secure"] : [])];
  if (!cfg) return [base, ...attrs, "Max-Age=0"].join("; ");
  const expires = String(Math.floor(Date.now() / 1000) + SESSION_SECONDS);
  return [`${base}${expires}.${sign(cfg, expires)}`, ...attrs, `Max-Age=${SESSION_SECONDS}`].join("; ");
}

function readCookie(req: Request): string | null {
  for (const part of (req.headers.get("cookie") || "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === COOKIE) return v.join("=");
  }
  return null;
}

/** Returns the config if the request carries a valid session, else null. */
export async function sessionConfig(req: Request): Promise<BoardConfig | null> {
  const value = readCookie(req);
  if (!value) return null;
  const [expires, sig] = value.split(".");
  if (!/^\d+$/.test(expires || "") || Number(expires) < Date.now() / 1000 || !sig) return null;
  const cfg = await loadConfig();
  return cfg && safeEqualHex(sig, sign(cfg, expires)) ? cfg : null;
}

/** Writes from the browser must carry this header: forces a CORS preflight other sites can't pass. */
export const fromBoard = (req: Request) => req.headers.get("x-bear-board") === "1";

export function agentAuthorized(req: Request): boolean {
  const expected = process.env.BOARD_AGENT_TOKEN_SHA256 || "";
  const token = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (!/^[0-9a-f]{64}$/.test(expected) || token.length < 32) return false;
  return safeEqualHex(sha256(token).toString("hex"), expected);
}

export const isSecure = (req: Request) => new URL(req.url).protocol === "https:";

export function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });
}
