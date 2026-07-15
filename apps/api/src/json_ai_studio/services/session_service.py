"""Session lifecycle + upload-into-session business logic."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..db.session_store import store
from .errors import NotFoundError

logger = logging.getLogger("json_ai_studio.session_service")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_session(name: str | None = None) -> dict[str, Any]:
    session = await store.create_session(name=name)
    logger.info("session created id=%s name=%r", session["id"], name)
    logger.debug("session created full=%s", session)
    return session


async def get_session(session_id: str) -> dict[str, Any]:
    """Return the session dict or raise NotFoundError."""
    session = await store.get_session(session_id)
    if session is None:
        logger.info("session lookup miss id=%s", session_id)
        raise NotFoundError("Session not found")
    logger.debug("session lookup hit id=%s full=%s", session_id, session)
    return session


async def create_from_template(
    json_doc: dict[str, Any],
    name: str | None = None,
    starter_prompts: list[str] | None = None,
) -> dict[str, Any]:
    """Create a session preloaded with static template JSON (ADR-0020).

    Reuses the ordinary session runtime — no new store, no version snapshot.
    `starter_prompts` are echoed back as transient response metadata for the
    studio's chip UI, not persisted into session state.
    """
    session = await store.create_session(name=name)
    working = json_doc if isinstance(json_doc, dict) else {}
    session["working_json"] = working
    session["baseline_json"] = working
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info(
        "session seeded from template id=%s top_keys=%d prompts=%d",
        session["id"],
        len(working),
        len(starter_prompts or []),
    )
    result = dict(session)
    result["starter_prompts"] = list(starter_prompts or [])
    return result


async def upload_json(data: Any, session_id: str | None) -> dict[str, Any]:
    """Store an uploaded JSON document; reuse the session if one is given."""
    logger.info(
        "upload_json session_id=%s type=%s top_keys=%s",
        session_id,
        type(data).__name__,
        list(data.keys()) if isinstance(data, dict) else None,
    )
    logger.debug("upload_json payload=%s", data)
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
    logger.info(
        "upload stored session_id=%s top_keys=%d",
        session["id"],
        len(session["working_json"]),
    )

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
