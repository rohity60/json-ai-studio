"""JSON upload endpoint: multipart form or raw JSON body."""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import require_api_key
from ..services import session_service

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/json/upload")
async def endpoint_upload_json(
    request: Request,
    _auth=Depends(require_api_key),
):
    """Accept a JSON body. Use existing session if provided."""
    content_type = request.headers.get("content-type", "")

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
            sid = raw_data.get("session_id") if isinstance(raw_data, dict) else None
            data = raw_data
        except (_json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON in upload body")

    return await session_service.upload_json(data, sid)
