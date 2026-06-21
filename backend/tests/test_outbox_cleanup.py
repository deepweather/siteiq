"""Outbox retention — old rows are deleted, recent rows survive."""
from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from pathlib import Path


def _make_db(tmp_path):
    from alembic import command
    from alembic.config import Config
    from db.engine import create_db_engine

    db = tmp_path / "outbox.db"
    url = f"sqlite+aiosqlite:///{db}"
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    command.upgrade(cfg, "head")
    return create_db_engine(url)


def test_cleanup_deletes_old_rows_only(tmp_path):
    from auth.outbox_cleanup import cleanup_once
    from auth.timeutil import utc_now
    from db.models import EmailOutbox, EmailStatus
    from sqlalchemy import select

    engine, factory = _make_db(tmp_path)

    async def _go():
        async with factory() as db:
            old = EmailOutbox(
                id=str(uuid.uuid4()),
                to_email="old@example.com",
                subject="old",
                html="",
                text="",
                status=EmailStatus.SENT.value,
                created_at=utc_now() - timedelta(days=120),
            )
            recent = EmailOutbox(
                id=str(uuid.uuid4()),
                to_email="recent@example.com",
                subject="recent",
                html="",
                text="",
                status=EmailStatus.SENT.value,
                created_at=utc_now() - timedelta(days=10),
            )
            db.add_all([old, recent])
            await db.commit()

        deleted = await cleanup_once(factory, retention_days=90)
        assert deleted == 1

        async with factory() as db:
            rows = (await db.execute(select(EmailOutbox))).scalars().all()
            emails = {r.to_email for r in rows}
        assert emails == {"recent@example.com"}
        await engine.dispose()

    asyncio.run(_go())


def test_cleanup_disabled_when_retention_zero(tmp_path):
    from auth.outbox_cleanup import cleanup_once

    engine, factory = _make_db(tmp_path)

    async def _go():
        deleted = await cleanup_once(factory, retention_days=0)
        assert deleted == 0
        await engine.dispose()

    asyncio.run(_go())
