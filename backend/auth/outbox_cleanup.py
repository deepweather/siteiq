"""Periodic email_outbox cleanup.

Without this the table grows linearly with traffic forever — fine in
dev, quietly expensive in prod (every send is a write, plus indexes).

The task runs at startup and then every `cleanup_interval_seconds` while
the app lives. It deletes rows older than `retention_days`. Set
`retention_days=0` to disable.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.timeutil import utc_now
from db.models import EmailOutbox


logger = logging.getLogger("siteiq.auth.outbox_cleanup")


async def cleanup_once(session_factory: async_sessionmaker, *, retention_days: int) -> int:
    """Delete outbox rows older than `retention_days`. Returns row count."""
    if retention_days <= 0:
        return 0
    cutoff = utc_now() - timedelta(days=retention_days)
    async with session_factory() as db:
        result = await db.execute(
            delete(EmailOutbox).where(EmailOutbox.created_at < cutoff)
        )
        await db.commit()
    deleted = result.rowcount or 0
    if deleted:
        logger.info(
            "email_outbox_cleaned",
            extra={"deleted": deleted, "retention_days": retention_days},
        )
    return deleted


async def run_cleanup_loop(
    session_factory: async_sessionmaker,
    *,
    retention_days: int,
    interval_seconds: int,
) -> None:
    """Background task: prune the outbox every `interval_seconds`."""
    if retention_days <= 0:
        logger.info("email_outbox_cleanup_disabled")
        return
    while True:
        try:
            await cleanup_once(session_factory, retention_days=retention_days)
        except Exception:
            logger.exception("email_outbox_cleanup_failed")
        await asyncio.sleep(interval_seconds)
