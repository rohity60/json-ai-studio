"""Async SQLAlchemy engine + session factory (ADR-0015).

Lazy singleton: `init_engine()` is called from the app lifespan. When
DATABASE_URL is unset, `session_factory()` returns None and the API runs
in anonymous-only mode (login returns 503). Non-request code (gateway
credit checks) uses `session_factory()` directly instead of Depends.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> None:
    """Create the engine once. No-op when DATABASE_URL unset or already up."""
    global _engine, _session_factory
    url = get_settings().database_url
    if url and _engine is None:
        _engine = create_async_engine(url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def session_factory() -> async_sessionmaker[AsyncSession] | None:
    """None => anonymous-only mode (no database configured)."""
    return _session_factory
