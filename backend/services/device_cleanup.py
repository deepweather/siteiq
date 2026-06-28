"""Background prune of evidence blobs past their retention window.

Mirrors `auth/outbox_cleanup.py`: drains on shutdown, retention `0` disables.
Keeps the in-DB `device_blobs` table from growing without bound while the
ledger itself (which only holds `blob:<id>` refs) stays small.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.models import DeviceBlob


logger = logging.getLogger("siteiq.device.cleanup")


async def run_cleanup_loop(
    session_factory: async_sessionmaker,
    *,
    retention_days: int,
    interval_seconds: int,
) -> None:
    if retention_days <= 0:
        logger.info("device_blob_cleanup_disabled")
        return
    while True:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        try:
            async with session_factory() as session:
                result = await session.execute(
                    delete(DeviceBlob).where(DeviceBlob.created_at < cutoff)
                )
                await session.commit()
                if result.rowcount:
                    logger.info(
                        "device_blobs_pruned", extra={"count": result.rowcount}
                    )
        except Exception:
            logger.exception("device_blob_cleanup_failed")
        await asyncio.sleep(interval_seconds)
