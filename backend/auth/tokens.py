"""Opaque token utilities.

We never store secrets at rest — only their sha256. `generate_token()`
returns the plaintext to embed in URLs; the caller stores
`hash_token(plaintext)` in the DB. Verification looks up by hash.

A constant-time `secrets.compare_digest` is unnecessary because we
look up by exact hash — no timing-correlated branch on the secret.
"""
from __future__ import annotations

import hashlib
import secrets


def generate_token(num_bytes: int = 32) -> str:
    """URL-safe high-entropy token. 32 bytes = 256 bits."""
    return secrets.token_urlsafe(num_bytes)


def hash_token(token: str) -> str:
    """sha256 hex digest (length 64). Constant-cost."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
