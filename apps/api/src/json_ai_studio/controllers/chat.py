"""SSE chat endpoint (ADR-0004)."""

from __future__ import annotations

import json as _json
import logging

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import Principal, get_principal
from ..services import chat_service, job_service, session_service
from ..services.intent import QUESTION, classify_intent
from ..services.errors import ConflictError, NotFoundError

logger = logging.getLogger("json_ai_studio.controllers.chat")

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def endpoint_chat(
    session_id: str = Form(...),
    message: str = Form(...),
    working_json_str: str | None = Form(default=None),
    thinking: bool = Form(default=False),
    focus_path: str | None = Form(default=None),
    principal: Principal = Depends(get_principal),
):
    """Send a chat turn; stream SSE response (ADR-0004)."""
    logger.info(
        "POST /api/chat principal=%s session=%s message_len=%d override_json=%s "
        "thinking=%s focus_path=%s",
        principal.kind,
        session_id,
        len(message),
        working_json_str is not None,
        thinking,
        focus_path,
    )
    try:
        session = await session_service.get_owned_session(session_id, principal)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # A review batch is in flight (ADR-0026): its diffs are about to land on
    # the document, so other edits wait; questions are still answered.
    if (
        job_service.running_job(session) is not None
        and classify_intent(message).kind != QUESTION
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_running",
                "hint": "Pause the review to make other edits.",
            },
        )

    try:
        working_json = (
            _json.loads(working_json_str)
            if working_json_str
            else session["working_json"]
        )
    except (_json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid working_json in request")

    return StreamingResponse(
        chat_service.chat_event_stream(
            session,
            working_json,
            message,
            principal,
            thinking=thinking,
            focus_path=focus_path,
        ),
        media_type="text/event-stream",
    )


_RESUME_HINTS = {
    "not_resumable": "Only the latest failed turn can be continued.",
    "resume_running": "This turn is already being continued.",
}


@router.post("/sessions/{session_id}/turns/{turn_id}/resume")
async def endpoint_resume_turn(
    session_id: str,
    turn_id: str,
    thinking: bool = Form(default=False),
    principal: Principal = Depends(get_principal),
):
    """Continue the latest failed chat turn; stream SSE (ADR-0028)."""
    logger.info(
        "POST /api/sessions/%s/turns/%s/resume principal=%s thinking=%s",
        session_id,
        turn_id,
        principal.kind,
        thinking,
    )
    try:
        session = await session_service.get_owned_session(session_id, principal)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if job_service.running_job(session) is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_running",
                "hint": "Pause the review to make other edits.",
            },
        )
    try:
        prepared = chat_service.prepare_resume(session, turn_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConflictError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=409,
            detail={"error": code, "hint": _RESUME_HINTS.get(code, code)},
        )
    return StreamingResponse(
        chat_service.resume_event_stream(
            session, prepared, principal, thinking=thinking
        ),
        media_type="text/event-stream",
    )
