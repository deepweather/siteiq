"""DB engine factory + migration smoke tests."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from db.engine import create_db_engine


def test_engine_factory_sqlite_file(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 't.db'}"
    engine, factory = create_db_engine(url)
    assert engine is not None
    assert factory is not None

    async def _go():
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT 1"))
            assert r.scalar() == 1
        await engine.dispose()

    asyncio.run(_go())


def test_engine_factory_in_memory_uses_static_pool():
    url = "sqlite+aiosqlite:///:memory:"
    engine, _ = create_db_engine(url)
    # Two sessions must observe the same in-memory database.
    from sqlalchemy.pool import StaticPool
    assert isinstance(engine.pool, StaticPool)

    async def _go():
        await engine.dispose()

    asyncio.run(_go())


def test_migrations_apply_to_fresh_sqlite(tmp_path):
    """Running alembic upgrade head must succeed on an empty SQLite file."""
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "fresh.db"
    url = f"sqlite+aiosqlite:///{db}"
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    command.upgrade(cfg, "head")

    # Confirm the users table exists.
    engine, _ = create_db_engine(url)

    async def _go():
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            tables = {row[0] for row in result.all()}
        await engine.dispose()
        return tables

    tables = asyncio.run(_go())
    assert "users" in tables
    assert "orgs" in tables
    assert "org_memberships" in tables
    assert "org_invites" in tables
    assert "auth_sessions" in tables
    assert "verification_tokens" in tables
    assert "email_outbox" in tables
    assert "audit_events" in tables
