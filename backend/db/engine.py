"""Async engine + session factory.

`create_db_engine(url)` returns (engine, session_factory). Tests use a
fresh in-memory or per-test SQLite file; the lifespan in `main.py` uses
the URL from Settings.

SQLite needs `check_same_thread=False` and `StaticPool` for in-memory
URLs so multiple async sessions see the same connection.
"""
from __future__ import annotations

from typing import Tuple

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


AsyncSessionFactory = async_sessionmaker[AsyncSession]


def create_db_engine(url: str, echo: bool = False) -> Tuple[AsyncEngine, AsyncSessionFactory]:
    """Build (engine, session_factory) for the given URL.

    SQLite gets a StaticPool when in-memory so multiple sessions share
    one connection; file-backed SQLite uses the default pool.
    """
    connect_args: dict = {}
    kwargs: dict = {"echo": echo, "future": True}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in url or url.endswith("///:memory:"):
            kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = connect_args

    engine = create_async_engine(url, **kwargs)
    session_factory: AsyncSessionFactory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory
