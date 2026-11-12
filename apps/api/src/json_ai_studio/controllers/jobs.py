"""Whole-document review jobs (ADR-0026): the client drives the batches."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import Principal, get_principal, require_api_key
from ..models import CreateJobRequest
from ..services import job_service
from ..services.errors import ConflictError, InvalidInputError, NotFoundError

logger = logging.getLogger("json_ai_studio.controllers.jobs")

router = APIRouter(prefix="/api", tags=["jobs"])

_CONFLICT_HINTS = {
    "job_running": "A batch is in flight. Wait for it to finish.",
    "job_finished": "This review is finished. Start a new one.",
}


@router.post("/sessions/{session_id}/jobs", status_code=201)
async def endpoint_create_job(
    session_id: str,
    req: CreateJobRequest,
    _auth=Depends(require_api_key),
):
    logger.info(
        "POST /api/sessions/%s/jobs principal=%s scope=%s instruction_len=%d",
        session_id,
        _auth.kind,
        req.scope_path,
        len(req.instruction),
    )
    try:
        return await job_service.create_job(
            session_id, req.scope_path, req.instruction, req.source_turn_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_active",
                "job_id": str(exc),
                "hint": "Finish or cancel the current review first.",
            },
        )


@router.get("/sessions/{session_id}/jobs/{job_id}")
async def endpoint_get_job(
    session_id: str,
    job_id: str,
    _auth=Depends(require_api_key),
):
    try:
        return await job_service.get_job(session_id, job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/sessions/{session_id}/jobs/{job_id}")
async def endpoint_cancel_job(
    session_id: str,
    job_id: str,
    _auth=Depends(require_api_key),
):
    logger.info(
        "DELETE /api/sessions/%s/jobs/%s principal=%s", session_id, job_id, _auth.kind
    )
    try:
        return await job_service.cancel_job(session_id, job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": str(exc), "hint": _CONFLICT_HINTS.get(str(exc))},
        )


@router.post("/sessions/{session_id}/jobs/{job_id}/next")
async def endpoint_next_batch(
    session_id: str,
    job_id: str,
    principal: Principal = Depends(get_principal),
):
    """Process exactly one batch; stream SSE (same budget/quota as chat)."""
    logger.info(
        "POST /api/sessions/%s/jobs/%s/next principal=%s",
        session_id,
        job_id,
        principal.kind,
    )
    try:
        session, job = await job_service.begin_next(session_id, job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": str(exc), "hint": _CONFLICT_HINTS.get(str(exc))},
        )
    return StreamingResponse(
        job_service.run_batch(session, job, principal),
        media_type="text/event-stream",
    )
