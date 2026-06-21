"""FastAPI dependency for async DB sessions.

Pulls the session factory off `request.app.state.db` (set by the lifespan)
and yields one session per request. No module-level globals.
"""
from __future__ import annotations

from typing import AsyncIterator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Database not ready")
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
