"""Periodic cleanup of expired auth state.

Without this, two tables grow forever:

- `auth_sessions`: every revoke/expire leaves the row behind for audit.
  After N days we drop the row entirely.
- `verification_tokens`: each signup, password reset, magic-link
  request adds a row. After expiry, they're useless.

Mirrors `auth/outbox_cleanup.py`. Both tasks run on the same schedule
out of the lifespan handler, drained on shutdown so the engine can
dispose cleanly.

Tunable via Settings:
- `auth_session_retention_days` (default 30) — for fully-revoked /
  fully-expired session rows. Live sessions are never touched.
- `auth_token_retention_days` (default 7) — for verification-token
  rows once they're past expiry. Anything still inside the validity
  window survives.
- `auth_cleanup_interval_seconds` (default 3600) — same cadence as
  the outbox cleanup so the loops align in logs.

Set retention to 0 to disable.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.timeutil import utc_now
from db.models import AuthSession, VerificationToken


logger = logging.getLogger("siteiq.auth.cleanup")


async def cleanup_once(
    session_factory: async_sessionmaker,
    *,
    session_retention_days: int,
    token_retention_days: int,
) -> dict[str, int]:
    """Single sweep. Returns row counts deleted per table."""
    out = {"auth_sessions": 0, "verification_tokens": 0}
    now = utc_now()

    if session_retention_days > 0:
        cutoff = now - timedelta(days=session_retention_days)
        async with session_factory() as db:
            result = await db.execute(
                delete(AuthSession).where(
                    or_(
                        # Revoked + retention window has elapsed.
                        AuthSession.revoked_at.is_not(None),
                        AuthSession.expires_at < now,
                    )
                ).where(AuthSession.last_seen_at < cutoff)
            )
            await db.commit()
        out["auth_sessions"] = result.rowcount or 0

    if token_retention_days > 0:
        cutoff = now - timedelta(days=token_retention_days)
        async with session_factory() as db:
            result = await db.execute(
                delete(VerificationToken).where(
                    or_(
                        VerificationToken.consumed_at.is_not(None),
                        VerificationToken.expires_at < now,
                    )
                ).where(VerificationToken.created_at < cutoff)
            )
            await db.commit()
        out["verification_tokens"] = result.rowcount or 0

    if any(out.values()):
        logger.info("auth_cleanup_swept", extra=out)
    return out


async def run_cleanup_loop(
    session_factory: async_sessionmaker,
    *,
    session_retention_days: int,
    token_retention_days: int,
    interval_seconds: int,
) -> None:
    """Background task: prune expired auth rows every `interval_seconds`."""
    if session_retention_days <= 0 and token_retention_days <= 0:
        logger.info("auth_cleanup_disabled")
        return
    while True:
        try:
            await cleanup_once(
                session_factory,
                session_retention_days=session_retention_days,
                token_retention_days=token_retention_days,
            )
        except Exception:
            logger.exception("auth_cleanup_failed")
        await asyncio.sleep(interval_seconds)
