"""Async + sync SQLAlchemy engines. SQLite in WAL mode per BUILDSPEC §3."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy import create_engine

from .config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)
AsyncSessionLocal = async_sessionmaker(
    async_engine, expire_on_commit=False, class_=AsyncSession
)

sync_engine = create_engine(
    settings.sync_database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False, class_=Session)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
    """Enable WAL + foreign keys on every connection. SQLite only."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()
    except Exception:
        # Non-SQLite connection; ignore.
        pass


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session() -> Session:
    return SyncSessionLocal()
