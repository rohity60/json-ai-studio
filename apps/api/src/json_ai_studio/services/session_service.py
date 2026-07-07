"""Session lifecycle + upload-into-session business logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..db.session_store import store
from .errors import NotFoundError


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_session(name: str | None = None) -> dict[str, Any]:
    return await store.create_session(name=name)


async def get_session(session_id: str) -> dict[str, Any]:
    """Return the session dict or raise NotFoundError."""
    session = await store.get_session(session_id)
    if session is None:
        raise NotFoundError("Session not found")
    return session


async def upload_json(data: Any, session_id: str | None) -> dict[str, Any]:
    """Store an uploaded JSON document; reuse the session if one is given."""
    session = await store.get_session(session_id) if session_id else None
    if session is None:
        name = data.get("name", "Uploaded") if isinstance(data, dict) else "Uploaded"
        session = await store.create_session(name=name)

    # Strip metadata before storing as working_json
    if isinstance(data, dict):
        data.pop("session_id", None)
        data.pop("name", None)
    session["working_json"] = data if isinstance(data, dict) else {}
    session["baseline_json"] = data if isinstance(data, dict) else {}
    session["updated_at"] = now_iso()
    await store.save_session(session)

    return {
        "session_id": session["id"],
        "before": session["baseline_json"],
        "after": session["working_json"],
        "diffs": [],
        "schema_summary": {
            "top_level_keys": list((data if isinstance(data, dict) else {}).keys()),
            "nested_depth": 0,
        },
    }
