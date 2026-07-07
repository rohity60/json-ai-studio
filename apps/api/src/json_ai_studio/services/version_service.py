"""Version snapshot business logic: create, select, list, bulk restore."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from ..db.session_store import store
from ..models import RestoreVersionsRequest, VersionSnapshot
from .errors import ConflictError, NotFoundError
from .session_service import get_session, now_iso


async def create_snapshot(
    session_id: str, label: str, json_data: dict[str, Any]
) -> dict[str, Any]:
    """Take a named snapshot of the current working JSON."""
    session = await get_session(session_id)

    versions_list = session.get("versions", [])
    parent = versions_list[-1] if versions_list else None
    parent_id = (
        (parent.id if hasattr(parent, "id") else parent.get("id")) if parent else None
    )
    version = VersionSnapshot(
        id=f"v{len(versions_list) + 1}",
        parent_id=parent_id,
        json_data=json_data,
        label=label,
        created_at=datetime.now(timezone.utc),
    )

    versions = list(versions_list)
    versions.append(version)
    session["versions"] = versions
    session["updated_at"] = now_iso()
    await store.save_session(session)
    return version.model_dump()


async def select_version(session_id: str, version_id: str) -> dict[str, Any]:
    """Reset working + baseline JSON to a snapshot; clear conversation."""
    session = await get_session(session_id)

    versions_list = session.get("versions", [])
    target = None
    for v in versions_list:
        vid = v.id if hasattr(v, "id") else v.get("id")
        if vid == version_id:
            target = v
            break

    if target is None:
        raise NotFoundError("Version not found")

    json_data = (
        target.json_data
        if hasattr(target, "json_data")
        else target.get("json_data", {})
    )
    session["working_json"] = copy.deepcopy(json_data)
    session["baseline_json"] = copy.deepcopy(json_data)
    session["active_version_id"] = version_id
    session["conversation_history"] = []
    session["updated_at"] = now_iso()
    await store.save_session(session)

    return {
        "working_json": session["working_json"],
        "baseline_json": session["baseline_json"],
        "active_version_id": session["active_version_id"],
        "versions": [
            v.model_dump() if hasattr(v, "model_dump") else v for v in versions_list
        ],
        "conversation_history": [],
    }


async def list_versions(session_id: str) -> dict[str, Any]:
    session = await get_session(session_id)
    versions = session.get("versions", [])
    return {
        "versions": [
            v.model_dump() if hasattr(v, "model_dump") else v for v in versions
        ],
        "count": len(versions),
    }


async def restore_versions(
    session_id: str, req: RestoreVersionsRequest
) -> dict[str, Any]:
    """Bulk-restore cached snapshots into an empty session.

    Snapshot ids, labels, parent chains, and timestamps are preserved
    verbatim so the browser cache round-trips losslessly. Only allowed
    when the session has no versions yet (409 otherwise) so client
    retries are safe.
    """
    session = await get_session(session_id)

    if session.get("versions"):
        raise ConflictError("Session already has versions")

    session["versions"] = [v.model_dump(mode="json") for v in req.versions]

    if req.working_json is not None:
        session["working_json"] = copy.deepcopy(req.working_json)
        session["baseline_json"] = copy.deepcopy(
            req.baseline_json if req.baseline_json is not None else req.working_json
        )
    elif req.baseline_json is not None:
        session["baseline_json"] = copy.deepcopy(req.baseline_json)

    restored_ids = {v.id for v in req.versions}
    session["active_version_id"] = (
        req.active_version_id if req.active_version_id in restored_ids else None
    )
    session["updated_at"] = now_iso()
    await store.save_session(session)
    return session
