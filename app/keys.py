"""API key generation, hashing and lookup.

Keys are shown to the user exactly once, at issue time. Only a SHA-256 digest is
stored, so a database dump -- or a backup on a laptop, or a support ticket with
a table attached -- does not hand over working credentials.

A plain fast hash is the right choice here, and deliberately not bcrypt/argon2:
an API key is 256 bits of CSPRNG output, so there is no dictionary to attack and
no realistic brute force. Key-stretching would buy nothing and add latency to
every request. Verification stays a single indexed lookup.

Key shape:  lxr_<43 url-safe chars>   e.g. lxr_kJ8mN2pQ...
  * the `lxr_` prefix makes keys identifiable in logs and greppable in a
    codebase where someone has pasted one by accident
  * url-safe base64 survives headers, query strings and shell quoting unharmed
  * `key_prefix` (the first 12 characters) is stored in the clear so a key can
    be named in a support conversation without being usable
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

KEY_PREFIX = "lxr_"
TOKEN_BYTES = 32          # 256 bits
PREFIX_LENGTH = 12        # characters of the key kept in plaintext for display


@dataclass(frozen=True)
class NewKey:
    """A freshly minted key. `secret` exists only in memory, only once."""

    secret: str           # the full key -- show to the user, never store
    key_hash: str         # SHA-256 hex, 64 chars -- this is what gets stored
    key_prefix: str       # first 12 chars, stored plaintext for identification


def hash_key(secret: str) -> str:
    """SHA-256 hex digest of a key. 64 characters, matching the column width."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_key() -> NewKey:
    secret = KEY_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    return NewKey(
        secret=secret,
        key_hash=hash_key(secret),
        key_prefix=secret[:PREFIX_LENGTH],
    )


def looks_like_key(value: str | None) -> bool:
    """Cheap shape check before touching the database.

    Rejects obviously malformed input without a query, which keeps scanners and
    typos off the connection pool. It is not a security control -- the hash
    lookup is -- so it stays deliberately permissive about length.
    """
    return bool(value) and value.startswith(KEY_PREFIX) and len(value) >= 20
