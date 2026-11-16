// Storage for the hosted board: Vercel Blob (private) in production, plain
// files under .board-data/ for local development. Everything stored here is
// either encrypted on the user's devices or a password verifier.
//
// Vercel Blob's Hobby tier allows ~2,000 uploads/listings a month and locks
// the store for 30 days past that, so callers keep writes rare and never list.

import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import { BlobNotFoundError, BlobPreconditionFailedError, get, put } from "@vercel/blob";

export class StoreConflict extends Error {}
export type Stored = { body: string; etag: string };

interface Store {
  read(key: string): Promise<Stored | null>;
  /** Writes `body`. With `ifMatch`, only if the stored ETag still matches (else StoreConflict). */
  write(key: string, body: string, ifMatch?: string): Promise<string>;
}

const blobStore: Store = {
  async read(key) {
    try {
      const res = await get(key, { access: "private", useCache: false });
      if (!res || res.statusCode !== 200) return null;
      return { body: await new Response(res.stream).text(), etag: res.blob.etag };
    } catch (e) {
      if (e instanceof BlobNotFoundError) return null;
      throw e;
    }
  },
  async write(key, body, ifMatch) {
    try {
      const res = await put(key, body, {
        access: "private",
        addRandomSuffix: false,
        allowOverwrite: true,
        contentType: "application/json",
        cacheControlMaxAge: 60,
        ...(ifMatch ? { ifMatch } : {}),
      });
      return res.etag;
    } catch (e) {
      if (e instanceof BlobPreconditionFailedError) throw new StoreConflict();
      throw e;
    }
  },
};

const DEV_DIR = path.join(process.cwd(), ".board-data");
const etagOf = (body: string) => createHash("sha256").update(body).digest("hex");
const fileStore: Store = {
  async read(key) {
    try {
      const body = await fs.readFile(path.join(DEV_DIR, key), "utf8");
      return { body, etag: etagOf(body) };
    } catch {
      return null;
    }
  },
  async write(key, body, ifMatch) {
    const file = path.join(DEV_DIR, key);
    if (ifMatch) {
      const current = await fileStore.read(key);
      if (!current || current.etag !== ifMatch) throw new StoreConflict();
    }
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, body);
    return etagOf(body);
  },
};

export function store(): Store {
  // Connecting a Blob store in Vercel sets BLOB_STORE_ID (the SDK then signs in with the
  // project's OIDC token); older setups and "read-write token" mode set BLOB_READ_WRITE_TOKEN.
  if (process.env.BLOB_STORE_ID || process.env.BLOB_READ_WRITE_TOKEN) return blobStore;
  if (process.env.NODE_ENV === "production") {
    throw new Error("Storage isn't connected. Add a Vercel Blob store to this project.");
  }
  return fileStore;
}

export async function readJSON<T>(key: string): Promise<{ value: T; etag: string } | null> {
  const got = await store().read(key);
  return got ? { value: JSON.parse(got.body) as T, etag: got.etag } : null;
}

/** Read-modify-write with optimistic concurrency, retried on conflict. */
export async function updateJSON<T>(key: string, fallback: T, change: (current: T) => T): Promise<T> {
  for (let attempt = 0; attempt < 5; attempt++) {
    const current = await readJSON<T>(key);
    const next = change(current ? current.value : structuredClone(fallback));
    try {
      await store().write(key, JSON.stringify(next), current?.etag);
      return next;
    } catch (e) {
      if (!(e instanceof StoreConflict)) throw e;
      await new Promise((r) => setTimeout(r, 100 * (attempt + 1)));
    }
  }
  throw new Error("The board is busy. Try again in a moment.");
}

export const KEYS = {
  config: "board/config.json",
  snapshot: "board/snapshot.json",
  queue: "board/queue.json",
} as const;
