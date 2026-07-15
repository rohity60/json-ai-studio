"""Session lifecycle endpoints."""

from __future__ import annotations

import json as _json
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..models import CreateSessionRequest, SeedFromTemplateRequest
from ..services import session_service
from ..services.errors import NotFoundError
from ..settings import get_settings

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


@router.post("/sessions/from-template", status_code=201)
async def endpoint_seed_from_template(
    req: SeedFromTemplateRequest,
    _auth=Depends(require_api_key),
):
    """Seed a new session from a static template (Open in Workspace, ADR-0020).

    Free (no LLM call); counts toward the request rate limit only. Anonymous
    callers are allowed. Logs a `template-open` line for the conversion metric.
    """
    size = len(_json.dumps(req.json_doc).encode("utf-8"))
    if size > get_settings().max_template_json_bytes:
        raise HTTPException(status_code=413, detail="Template JSON too large")

    logger.info(
        "POST /api/sessions/from-template principal=%s template_slug=%s json_bytes=%d",
        _auth.kind,
        req.templateSlug,
        size,
    )

    return await session_service.create_from_template(
        json_doc=req.json_doc,
        name=req.templateTitle or req.templateSlug,
        starter_prompts=req.starterPrompts,
    )


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
