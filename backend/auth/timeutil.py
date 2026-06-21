"""Timezone normalization for SQLite.

SQLite (via aiosqlite) returns naive datetimes even when the column is
declared `DateTime(timezone=True)`. Postgres returns aware datetimes
correctly. We always assume UTC at rest, so coerce naive values to
UTC-aware on read.
"""
from __future__ import annotations

from datetime import datetime, timezone


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
