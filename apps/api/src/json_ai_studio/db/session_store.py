"""Session persistence layer (ADR-0013, amends ADR-0006).

``SessionStore`` is the abstract interface; ``InMemorySessionStore`` is the
MVP implementation backed by a plain dict. The interface is async so a
future DB-backed implementation (asyncpg / async SQLAlchemy) can slot in
without an interface break.

Call-site discipline: always get -> mutate -> save. The in-memory store
returns live references, which makes ``save_session`` technically
redundant here, but a DB implementation will return detached copies --
skipping ``save_session`` would silently lose writes there.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class SessionStore(ABC):
    """Abstract session persistence."""

    @abstractmethod
    async def create_session(self, *, name: str | None = None) -> dict[str, Any]:
        """Create and persist a new session; return the full session dict."""

    @abstractmethod
    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return session dict or None."""

    @abstractmethod
    async def save_session(self, session: dict[str, Any]) -> None:
        """Persist a session dict back to the store."""

    @abstractmethod
    async def list_sessions(self) -> list[str]:
        """Return all known session IDs."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Remove a session. Returns True if it existed."""


class InMemorySessionStore(SessionStore):
    """Dict-backed store. No TTL -- sessions live until server restart."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    async def create_session(self, *, name: str | None = None) -> dict[str, Any]:
        sid = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        session: dict[str, Any] = {
            "id": sid,
            "name": name,
            "working_json": {},
            "baseline_json": {},
            "versions": [],
            "conversation_history": [],
            "applied_diffs": [],
            "rejected_diffs": [],
            "active_version_id": None,
            "created_at": now,
            "updated_at": now,
        }
        self._sessions[sid] = session
        return session

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    async def save_session(self, session: dict[str, Any]) -> None:
        self._sessions[session["id"]] = session

    async def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    async def delete_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None


store: SessionStore = InMemorySessionStore()


def get_store() -> SessionStore:
    """Return the active store. Swap point for a future DB implementation."""
    return store
