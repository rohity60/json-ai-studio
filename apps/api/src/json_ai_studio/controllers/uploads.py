"""JSON upload endpoint: multipart form or raw JSON body."""

from __future__ import annotations

import json as _json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import require_api_key
from ..services import session_service

logger = logging.getLogger("json_ai_studio.controllers.uploads")

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/json/upload")
async def endpoint_upload_json(
    request: Request,
    _auth=Depends(require_api_key),
):
    """Accept a JSON body. Use existing session if provided."""
    content_type = request.headers.get("content-type", "")
    logger.info(
        "POST /api/json/upload principal=%s content_type=%s",
        _auth.kind,
        content_type,
    )

    sid = None
    if "multipart/form-data" in content_type:
        form = await request.form()
        sid = form.get("session_id", None)  # Reuse from frontend if present
        raw = form.get("json_body", "{}")
        try:
            data = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid JSON in upload body")
    else:
        body_bytes = await request.body()
        try:
            raw_data = _json.loads(body_bytes.decode("utf-8"))
            # Raw-body uploads smuggle session_id inside the document itself —
            # pop it here so the stored JSON is exactly what the user sent.
            sid = (
                raw_data.pop("session_id", None) if isinstance(raw_data, dict) else None
            )
            data = raw_data
        except (_json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON in upload body")

    return await session_service.upload_json(data, sid)
