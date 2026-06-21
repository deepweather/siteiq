"""argon2 password hashing — round-trip + cost knobs."""
from __future__ import annotations

from auth.passwords import cheap_hasher, hash_password, verify_password


def test_round_trip():
    h = cheap_hasher()
    digest = hash_password("correct-horse-battery-staple", hasher=h)
    assert digest != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", digest, hasher=h)


def test_wrong_password_rejected():
    h = cheap_hasher()
    digest = hash_password("hunter2-and-then-some", hasher=h)
    assert not verify_password("nope", digest, hasher=h)


def test_invalid_hash_returns_false():
    h = cheap_hasher()
    assert verify_password("anything", "not-an-argon2-hash", hasher=h) is False


def test_two_hashes_of_same_password_differ():
    h = cheap_hasher()
    a = hash_password("same-input", hasher=h)
    b = hash_password("same-input", hasher=h)
    assert a != b  # argon2 includes a per-hash salt
    assert verify_password("same-input", a, hasher=h)
    assert verify_password("same-input", b, hasher=h)
