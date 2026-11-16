// Shape checks for encrypted payloads. The server can't read them, only bound their size.
export type Envelope = { v: 1; iv: string; ct: string };
export type QueuedEdit = { id: string; at: string; envelope: Envelope };
export type Queue = { edits: QueuedEdit[] };
export type SnapshotRecord = { updatedAt: string; envelope: Envelope };

const B64 = /^[A-Za-z0-9+/]+={0,2}$/;
export function isEnvelope(x: unknown, maxBytes: number): x is Envelope {
  const e = x as Envelope;
  return !!e && e.v === 1 && typeof e.iv === "string" && typeof e.ct === "string"
    && e.iv.length === 16 && B64.test(e.iv) && B64.test(e.ct) && e.ct.length <= maxBytes;
}
export const MAX_EDIT = 200_000;          // base64 chars
export const MAX_SNAPSHOT = 4_000_000;
export const MAX_QUEUE = 500;
