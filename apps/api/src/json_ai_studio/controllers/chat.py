"""SSE chat endpoint (ADR-0004)."""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import require_api_key
from ..services import chat_service, session_service
from ..services.errors import NotFoundError

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def endpoint_chat(
    session_id: str = Form(...),
    message: str = Form(...),
    working_json_str: str | None = Form(default=None),
    _auth=Depends(require_api_key),
):
    """Send a chat turn; stream SSE response (ADR-0004)."""
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
        chat_service.chat_event_stream(session, working_json, message, _auth),
        media_type="text/event-stream",
    )
