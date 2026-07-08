"""Explain endpoint: LLM-generated markdown summary of the working JSON."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..auth import Principal, get_principal
from ..gateway import GatewayService
from ..services import session_service
from ..services.errors import NotFoundError

router = APIRouter(prefix="/api", tags=["chat"])

logger = logging.getLogger("json_ai_studio.explain")


@router.post("/explain")
async def endpoint_explain(
    body: dict[str, Any],
    principal: Principal = Depends(get_principal),
):
    """Explain the JSON in a session. Returns markdown as plain text."""
    session_id = body.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId is required")

    try:
        session = await session_service.get_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    working_json = body.get("workingJson", session.get("working_json", {}))
    if not isinstance(working_json, dict):
        working_json = {}

    try:
        markdown = await GatewayService.explain(session_id, principal, working_json)
    except HTTPException:
        # Rate limit / credit errors (429/402) must reach the client with their
        # own status, not be swallowed into a generic 500.
        raise
    except Exception as e:
        logger.exception("explain failed session=%s", session_id)
        raise HTTPException(status_code=500, detail=f"Explain failed: {e}")

    return Response(content=markdown, media_type="text/plain")
