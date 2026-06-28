"""In-memory SessionStore (ADR-0006).

Single global dict with auto-generated UUIDs. No TTL -- sessions live until
server restart. Easy to swap for a disk/DB layer later.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

_sessions: dict[str, dict[str, Any]] = {}


def create_session(*, name: str | None = None) -> str:
    """Create a new session. Returns the session ID."""
    sid = uuid4().hex
    _sessions[sid] = {
        "id": sid,
        "name": name,
        "working_json": {},
        "baseline_json": {},
        "versions": [],
        "conversation_history": [],
        "applied_diffs": [],
        "created_at": "",  # Filled by caller with ISO timestamp
        "updated_at": "",  # Filled by caller with ISO timestamp
    }
    return sid


def get_session(session_id: str) -> dict[str, Any] | None:
    """Return session dict or None."""
    return _sessions.get(session_id)


def save_session(session: dict[str, Any]) -> None:
    """Persist a session dict back to the store."""
    _sessions[session["id"]] = session


def list_sessions() -> list[str]:
    """Return all known session IDs."""
    return list(_sessions.keys())


def delete_session(session_id: str) -> bool:
    """Remove a session. Returns True if it existed."""
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
