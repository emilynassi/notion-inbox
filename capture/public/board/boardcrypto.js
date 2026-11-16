// End-to-end encryption for the hosted Bear Board (format v1).
// Mirrored in bear_board/boardcrypto.py; the two must stay byte-compatible.
//
//   master  = PBKDF2-HMAC-SHA256(password, kdfSalt, iterations) → 32 bytes
//   authKey = HKDF-SHA256(master, info "bear-board auth v1") → sent to the server to sign in
//   encKey  = HKDF-SHA256(master, info "bear-board enc v1")  → never leaves the device
//   server stores only SHA-256(authKey), so it can check sign-ins but can't decrypt.
//
//   envelope = { v: 1, iv: base64(12 bytes), ct: base64(AES-256-GCM ciphertext+tag) }
//   AAD = the purpose ("snapshot" or "edit"), so one kind can't be passed off as the other.
//   Snapshots are gzipped before encryption; edits are plain JSON.
(() => {
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  const subtle = globalThis.crypto.subtle;

  const b64 = (bytes) => {
    let s = "";
    for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
    return btoa(s);
  };
  const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const hex = (bytes) => [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const unhex = (s) => Uint8Array.from(s.match(/../g) || [], (h) => parseInt(h, 16));

  async function hkdf(master, info, usages, extractable = false) {
    const base = await subtle.importKey("raw", master, "HKDF", false, ["deriveKey", "deriveBits"]);
    const params = { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: enc.encode(info) };
    if (usages === "bits") return new Uint8Array(await subtle.deriveBits(params, base, 256));
    return subtle.deriveKey(params, base, { name: "AES-GCM", length: 256 }, extractable, usages);
  }

  /** Returns { authKeyHex, encKey } where encKey is a non-extractable CryptoKey. */
  async function deriveKeys(password, kdfSaltHex, iterations) {
    const pw = await subtle.importKey("raw", enc.encode(password.normalize("NFC")), "PBKDF2", false, ["deriveBits"]);
    const master = new Uint8Array(await subtle.deriveBits(
      { name: "PBKDF2", hash: "SHA-256", salt: unhex(kdfSaltHex), iterations }, pw, 256));
    const authKey = await hkdf(master, "bear-board auth v1", "bits");
    const encKey = await hkdf(master, "bear-board enc v1", ["encrypt", "decrypt"]);
    master.fill(0);
    return { authKeyHex: hex(authKey), encKey };
  }

  async function gzip(bytes) {
    return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new CompressionStream("gzip"))).arrayBuffer());
  }
  async function gunzip(bytes) {
    return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer());
  }

  async function seal(encKey, purpose, value) {
    let data = enc.encode(JSON.stringify(value));
    if (purpose === "snapshot") data = await gzip(data);
    const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
    const ct = await subtle.encrypt({ name: "AES-GCM", iv, additionalData: enc.encode(purpose) }, encKey, data);
    return { v: 1, iv: b64(iv), ct: b64(ct) };
  }

  async function open(encKey, purpose, envelope) {
    if (!envelope || envelope.v !== 1) throw new Error("Unknown data format");
    let data = new Uint8Array(await subtle.decrypt(
      { name: "AES-GCM", iv: unb64(envelope.iv), additionalData: enc.encode(purpose) }, encKey, unb64(envelope.ct)));
    if (purpose === "snapshot") data = await gunzip(data);
    return JSON.parse(dec.decode(data));
  }

  globalThis.BoardCrypto = { deriveKeys, seal, open };
})();
