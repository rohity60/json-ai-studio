"""Session lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..models import CreateSessionRequest
from ..services import session_service
from ..services.errors import NotFoundError

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/sessions")
async def endpoint_create_session(
    req: CreateSessionRequest,
    _auth=Depends(require_api_key),
):
    """Create a new session. Returns session ID and initial state."""
    return await session_service.create_session(name=req.name)


@router.get("/sessions/{session_id}")
async def endpoint_get_session(
    session_id: str,
    _auth=Depends(require_api_key),
):
    """Retrieve full session state."""
    try:
        return await session_service.get_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
