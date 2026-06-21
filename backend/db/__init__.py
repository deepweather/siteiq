"""Database layer.

Async SQLAlchemy 2.0 engine + session factory. The engine URL switches
between SQLite (dev/test) and Postgres (prod) via Settings — schemas only
use portable types (UUIDs as String(36), JSON as JSON) so the same
migrations run on both backends.
"""
from __future__ import annotations

from db.base import Base
from db.engine import create_db_engine, AsyncSessionFactory
from db.session import get_db

__all__ = ["Base", "create_db_engine", "AsyncSessionFactory", "get_db"]
