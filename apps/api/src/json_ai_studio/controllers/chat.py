"""SSE chat endpoint (ADR-0004)."""

from __future__ import annotations

import json as _json
import logging

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import Principal, get_principal
from ..services import chat_service, session_service
from ..services.errors import NotFoundError

logger = logging.getLogger("json_ai_studio.controllers.chat")

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def endpoint_chat(
    session_id: str = Form(...),
    message: str = Form(...),
    working_json_str: str | None = Form(default=None),
    principal: Principal = Depends(get_principal),
):
    """Send a chat turn; stream SSE response (ADR-0004)."""
    logger.info(
        "POST /api/chat principal=%s session=%s message_len=%d override_json=%s",
        principal.kind,
        session_id,
        len(message),
        working_json_str is not None,
    )
    try:
        session = await session_service.get_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        working_json = (
            _json.loads(working_json_str)
            if working_json_str
            else session["working_json"]
        )
    except (_json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid working_json in request")

    return StreamingResponse(
        chat_service.chat_event_stream(session, working_json, message, principal),
        media_type="text/event-stream",
    )
