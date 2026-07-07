"""Version snapshot endpoints: create, select, list, bulk restore."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..models import (
    CreateVersionRequest,
    RestoreVersionsRequest,
    SelectVersionRequest,
)
from ..services import version_service
from ..services.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/sessions/{session_id}/versions")
async def endpoint_create_version_snapshot(
    session_id: str,
    req: CreateVersionRequest,
    _auth=Depends(require_api_key),
):
    """Create a named snapshot of the current working JSON."""
    try:
        return await version_service.create_snapshot(
            session_id, req.label, req.json_data
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions/{session_id}/versions/select")
async def endpoint_select_version(
    session_id: str,
    req: SelectVersionRequest,
    _auth=Depends(require_api_key),
):
    """Select a version snapshot as the new working baseline."""
    try:
        return await version_service.select_version(session_id, req.versionId)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions/{session_id}/versions")
async def endpoint_list_versions(
    session_id: str,
    _auth=Depends(require_api_key),
):
    """List all version snapshots for a session (V-10)."""
    try:
        return await version_service.list_versions(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions/{session_id}/versions/restore")
async def endpoint_restore_versions(
    session_id: str,
    req: RestoreVersionsRequest,
    _auth=Depends(require_api_key),
):
    """Bulk-restore cached version snapshots into an empty session.

    Used by the frontend to rehydrate a fresh session from the browser's
    IndexedDB cache after a backend restart.
    """
    try:
        return await version_service.restore_versions(session_id, req)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
