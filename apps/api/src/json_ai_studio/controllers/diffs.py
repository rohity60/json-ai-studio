"""Diff accept/reject endpoints (single + batch)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..diff_utils import DiffApplyError
from ..services import diff_service
from ..services.errors import NotFoundError

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/sessions/{session_id}/diffs/accept-all")
async def endpoint_accept_all_diffs(
    session_id: str,
    _auth=Depends(require_api_key),
):
    try:
        return await diff_service.accept_all(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions/{session_id}/diffs/reject-all")
async def endpoint_reject_all_diffs(
    session_id: str,
    _auth=Depends(require_api_key),
):
    try:
        return await diff_service.reject_all(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions/{session_id}/diffs/{diff_id}/accept")
async def endpoint_accept_single_diff(
    session_id: str,
    diff_id: str,
    _auth=Depends(require_api_key),
):
    """Accept a single diff by ID: promote it into baseline_json."""
    try:
        return await diff_service.accept_one(session_id, diff_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DiffApplyError as exc:
        raise HTTPException(
            status_code=422, detail=f"Cannot accept diff {diff_id}: {exc}"
        )


@router.post("/sessions/{session_id}/diffs/{diff_id}/reject")
async def endpoint_reject_single_diff(
    session_id: str,
    diff_id: str,
    _auth=Depends(require_api_key),
):
    """Reject a single diff by ID: revert it from working_json."""
    try:
        return await diff_service.reject_one(session_id, diff_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DiffApplyError as exc:
        raise HTTPException(
            status_code=422, detail=f"Cannot reject diff {diff_id}: {exc}"
        )
