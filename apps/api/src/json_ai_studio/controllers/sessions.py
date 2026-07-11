"""Session lifecycle endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..models import CreateSessionRequest
from ..services import session_service
from ..services.errors import NotFoundError

logger = logging.getLogger("json_ai_studio.controllers.sessions")

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/sessions")
async def endpoint_create_session(
    req: CreateSessionRequest,
    _auth=Depends(require_api_key),
):
    """Create a new session. Returns session ID and initial state."""
    logger.info("POST /api/sessions principal=%s name=%r", _auth.kind, req.name)
    return await session_service.create_session(name=req.name)


@router.get("/sessions/{session_id}")
async def endpoint_get_session(
    session_id: str,
    _auth=Depends(require_api_key),
):
    """Retrieve full session state."""
    logger.info("GET /api/sessions/%s principal=%s", session_id, _auth.kind)
    try:
        return await session_service.get_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
