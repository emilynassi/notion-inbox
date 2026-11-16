"""End-to-end encryption for the hosted Bear Board (format v1).

Mirror of capture/public/board/boardcrypto.js; the two must stay byte-compatible.
See that file for the scheme. Needs the `cryptography` package.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import unicodedata

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 600_000


def _hkdf(master: bytes, info: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info.encode()).derive(master)


def derive_keys(password: str, kdf_salt_hex: str, iterations: int = ITERATIONS) -> tuple[bytes, bytes]:
    """Returns (auth_key, enc_key)."""
    master = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=bytes.fromhex(kdf_salt_hex),
                        iterations=iterations).derive(unicodedata.normalize("NFC", password).encode())
    return _hkdf(master, "bear-board auth v1"), _hkdf(master, "bear-board enc v1")


def auth_verifier(auth_key: bytes) -> str:
    return hashlib.sha256(auth_key).hexdigest()


def seal(enc_key: bytes, purpose: str, value) -> dict:
    data = json.dumps(value, separators=(",", ":")).encode()
    if purpose == "snapshot":
        data = gzip.compress(data, mtime=0)
    iv = os.urandom(12)
    ct = AESGCM(enc_key).encrypt(iv, data, purpose.encode())
    return {"v": 1, "iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(ct).decode()}


def open_(enc_key: bytes, purpose: str, envelope: dict):
    if not isinstance(envelope, dict) or envelope.get("v") != 1:
        raise ValueError("Unknown data format")
    data = AESGCM(enc_key).decrypt(base64.b64decode(envelope["iv"]), base64.b64decode(envelope["ct"]), purpose.encode())
    if purpose == "snapshot":
        data = gzip.decompress(data)
    return json.loads(data)
