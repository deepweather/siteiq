"""Alembic env — runs migrations against SQLite (dev/test) and Postgres
(prod) without changes.

The URL is read from SITEIQ_DATABASE_URL env var (or falls back to the
alembic.ini default), so `uv run alembic upgrade head` works in both
environments.

We use an async engine + `run_sync` because the project's runtime engine
is async; sharing the same URL surface means dev and prod see identical
schemas.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make the backend package importable regardless of where Alembic is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.base import Base  # noqa: E402
import db.models  # noqa: F401, E402  -- import side-effect: register tables


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Allow runtime override of the DB URL.
url_override = os.environ.get("SITEIQ_DATABASE_URL")
if url_override:
    config.set_main_option("sqlalchemy.url", url_override)

target_metadata = Base.metadata


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _do_run_migrations(connection) -> None:
    url = config.get_main_option("sqlalchemy.url") or ""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite needs batch mode for ALTER operations to work in any future
        # migrations; safe to enable always.
        render_as_batch=_is_sqlite(url),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(url or ""),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
