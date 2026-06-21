"""Password hashing — argon2id via argon2-cffi.

The hasher is module-local because PasswordHasher is cheap to construct
and stateless. We pin params on the conservative side of the OWASP
recommendation; tests can use a faster `cheap_hasher()` to keep the
suite quick.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


# OWASP-recommended argon2id baseline (memory in KiB).
# 19 MiB / 2 iterations / parallelism 1 — good for a server with cold
# CPU, well under the 19MB-per-login cap for a busy login endpoint.
_DEFAULT = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1, hash_len=32)


def hash_password(plain: str, hasher: PasswordHasher | None = None) -> str:
    return (hasher or _DEFAULT).hash(plain)


def verify_password(plain: str, hashed: str, hasher: PasswordHasher | None = None) -> bool:
    h = hasher or _DEFAULT
    try:
        return h.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def cheap_hasher() -> PasswordHasher:
    """For tests. Drops time_cost so suites run fast."""
    return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1, hash_len=16)
