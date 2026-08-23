"""Lazy engine/session-factory.

Deliberately NOT created at import time (unlike npm_client/proxmox_client in app.main) so tests
can point settings.database_path at a temp file before the engine is first touched. Call
reset_engine_for_tests() if settings.database_path changes after the engine was already created.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.base import Base

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _database_url() -> str:
    path = Path(settings.database_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{path}"


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(_database_url())
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def init_models() -> None:
    """Create tables directly from the ORM metadata.

    Used for local dev/tests (fast, no migration history needed). Production containers run
    `alembic upgrade head` instead so the persistent volume gets versioned migrations.
    """
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def reset_engine_for_tests() -> None:
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
