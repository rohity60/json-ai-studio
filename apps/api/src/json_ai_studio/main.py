"""JSON AI Studio -- FastAPI backend.

All endpoints from openapi/spec.yaml. SSE streaming for /api/chat
(ADR-0004). In-memory session store (ADR-0006). Fail-fast errors (ADR-0007).
Uses litellm pointed at the deployment registry backends.

Auth: all endpoints protected by X-API-Key header + rate limiter (10 req/min per key).
"""

from __future__ import annotations

import copy
import json as _json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .auth import require_api_key
from .diff_utils import DiffApplyError, DiffUtils, parse_llm_response
from .gateway import GatewayService
from .logging_config import configure as _configure_logging
from .models import (
    CreateSessionRequest,
    CreateVersionRequest,
    SelectVersionRequest,
    VersionSnapshot,
)
from .prompting import EXPLAIN_TEMPLATE, build_system_prompt
from .store import create_session as _new_session
from .store import get_session, save_session

app = FastAPI(title="JSON AI Studio API", version="0.1.0")

# CORS -- handle OPTIONS preflight for fetch with X-API-Key header
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "x-api-key"],
    max_age=86400,
)

logger = logging.getLogger("json_ai_studio.main")
_configure_logging()


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(event: str, payload: dict[str, Any]) -> str:
    """Format one spec-compliant SSE event block."""
    return f"event: {event}\ndata: {_json.dumps(payload)}\n\n"


def _parse_sse(event_text: str) -> tuple[str | None, dict[str, Any] | None]:
    """Parse one SSE block back into (event_name, payload).

    Tolerates both the spec-compliant "data: {...}" form and the legacy
    "data{...}" form so mixed streams keep working.
    """
    event: str | None = None
    data_lines: list[str] = []
    for line in event_text.split("\n"):
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        elif line.startswith("data"):
            data_lines.append(line[len("data") :].strip())
    if not data_lines:
        return event, None
    try:
        return event, _json.loads("\n".join(data_lines))
    except (_json.JSONDecodeError, ValueError):
        return event, None


# ---------------------------------------------------------------------------
# SSE Chat Streaming (ADR-0004)
# ---------------------------------------------------------------------------


async def _stream_llm(
    working_json: dict[str, Any], message: str, api_key: str
) -> AsyncGenerator[str, None]:
    """Stream LLM response as SSE events via GatewayService.

    Event sequence: thinking -> diff(s) -> complete (ADR-0004).
    Parses the LLM output into diffs, applies only the ones that
    resolve against the current document, and emits diff events solely
    for those. The complete event carries the merged JSON plus a
    human-readable explanation (never raw model output when diffs
    parsed successfully).
    """
    try:
        yield _sse("thinking", {"text": "Analyzing your request..."})

        system_prompt = build_system_prompt(working_json)

        content_parts: list[str] = []
        error_payload: dict[str, Any] | None = None
        async for event_text in GatewayService.invoke(
            "chat-session", message, api_key, system_prompt
        ):
            yield event_text
            event, payload = _parse_sse(event_text)
            if event == "thinking" and payload is not None:
                text = payload.get("text")
                if isinstance(text, str):
                    content_parts.append(text)
            elif event == "error" and payload is not None:
                error_payload = payload

        combined = "".join(content_parts)
        logger.info("chat stream finished response_len=%d", len(combined))
        logger.info("llm raw output: %s", combined[:2000])

        if error_payload is not None:
            yield _sse(
                "complete",
                {
                    "working_json": working_json,
                    "explanation": (
                        "The AI request failed: "
                        f"{error_payload.get('error', 'unknown error')}. "
                        "No changes were made."
                    ),
                },
            )
            return

        diffs, explanation = parse_llm_response(combined)
        logger.info(
            "parsed llm response: diffs=%d explanation=%r",
            len(diffs),
            explanation[:300],
        )

        if not diffs:
            logger.warning(
                "no diffs parsed from llm output (len=%d); "
                "returning explanation only",
                len(combined),
            )
            yield _sse(
                "complete",
                {
                    "working_json": working_json,
                    "explanation": explanation
                    or combined
                    or "The model returned no changes.",
                },
            )
            return

        merged, applied, failed = DiffUtils.apply_all_verbose(diffs, working_json)
        logger.info(
            "diff application: applied=%d failed=%d%s",
            len(applied),
            len(failed),
            " reasons=" + "; ".join(r for _, r in failed) if failed else "",
        )

        for diff in applied:
            entry = {**diff, "id": str(uuid4())}
            yield _sse("diff", {"entry": entry})

        notes: list[str] = []
        if explanation:
            notes.append(explanation)
        elif applied:
            notes.append(f"Applied {len(applied)} change(s).")
        if failed:
            failed_desc = "; ".join(
                f"{d.get('path')} ({reason})" for d, reason in failed
            )
            notes.append(
                f"Skipped {len(failed)} proposed change(s) that did not match "
                f"the current JSON: {failed_desc}."
            )
        yield _sse(
            "complete",
            {
                "working_json": merged,
                "explanation": " ".join(notes) or "Done.",
            },
        )

    except Exception as e:
        # Fail-fast error (ADR-0007): yield error in stream, don't retry
        logger.exception("chat stream failed")
        yield _sse(
            "complete",
            {"working_json": working_json, "explanation": f"Error: {e}"},
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health_check():
    """Health check endpoint. No auth required."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/")
def root():
    """Root endpoint. No auth required (docs only)."""
    return {
        "service": "JSON AI Studio API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "sessions_post": "POST /api/sessions",
            "upload": "POST /api/json/upload",
            "chat": "POST /api/chat",
            "versions_get": "GET /api/sessions/{id}/versions",
            "versions_post": "POST /api/sessions/{id}/versions",
            "versions_select": "POST /api/sessions/{id}/versions/select",
            "diff_accept": "POST /api/sessions/{id}/diffs/{diffId}/accept",
            "diff_reject": "POST /api/sessions/{id}/diffs/{diffId}/reject",
            "diff_accept_all": "POST /api/sessions/{id}/diffs/accept-all",
            "diff_reject_all": "POST /api/sessions/{id}/diffs/reject-all",
        },
    }


@app.post("/api/sessions")
async def endpoint_create_session(
    req: CreateSessionRequest,
    _auth=Depends(require_api_key),
):
    """Create a new session. Returns session ID and initial state."""
    sid = _new_session(name=req.name)
    session = get_session(sid)
    if session is None:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return session


@app.get("/api/sessions/{session_id}")
async def endpoint_get_session(
    session_id: str,
    _auth=Depends(require_api_key),
):
    """Retrieve full session state."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/api/sessions/{session_id}/versions")
async def endpoint_create_version_snapshot(
    session_id: str,
    req: CreateVersionRequest,
    _auth=Depends(require_api_key),
):
    """Create a named snapshot of the current working JSON."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    versions_list = session.get("versions", [])
    parent = versions_list[-1] if versions_list else None
    parent_id = parent.id if parent else None
    version = VersionSnapshot(
        id=f"v{len(versions_list) + 1}",
        parent_id=parent_id,
        json_data=req.json_data,
        label=req.label,
        created_at=datetime.now(timezone.utc),
    )

    versions = list(session.get("versions", []))
    versions.append(version)
    session["versions"] = versions
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return version.model_dump()


@app.post("/api/sessions/{session_id}/versions/select")
async def endpoint_select_version(
    session_id: str,
    req: SelectVersionRequest,
    _auth=Depends(require_api_key),
):
    """Select a version snapshot as the new working baseline."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    version_id = req.versionId
    versions_list = session.get("versions", [])
    target = None
    for v in versions_list:
        vid = v.id if hasattr(v, "id") else v.get("id")
        if vid == version_id:
            target = v
            break

    if target is None:
        raise HTTPException(status_code=404, detail="Version not found")

    json_data = (
        target.json_data
        if hasattr(target, "json_data")
        else target.get("json_data", {})
    )
    session["working_json"] = copy.deepcopy(json_data)
    session["baseline_json"] = copy.deepcopy(json_data)
    session["active_version_id"] = version_id
    session["conversation_history"] = []
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)

    return {
        "working_json": session["working_json"],
        "baseline_json": session["baseline_json"],
        "active_version_id": session["active_version_id"],
        "versions": [
            v.model_dump() if hasattr(v, "model_dump") else v for v in versions_list
        ],
        "conversation_history": [],
    }


@app.get("/api/sessions/{session_id}/versions")
async def endpoint_list_versions(
    session_id: str,
    _auth=Depends(require_api_key),
):
    """List all version snapshots for a session (V-10)."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    versions = session.get("versions", [])
    return {
        "versions": [
            v.model_dump() if hasattr(v, "model_dump") else v for v in versions
        ],
        "count": len(versions),
    }


@app.post("/api/json/upload")
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

    # Reuse existing session or create new
    if sid and get_session(sid):
        session = get_session(sid)
    else:
        sid = _new_session(
            name=data.get("name", "Uploaded") if isinstance(data, dict) else "Uploaded"
        )
        session = get_session(sid)
        if session is None:
            raise HTTPException(
                status_code=500, detail="Failed to create session after upload"
            )

    # Strip metadata before storing as working_json
    if isinstance(data, dict):
        data.pop("session_id", None)
        data.pop("name", None)
    session["working_json"] = data if isinstance(data, dict) else {}
    session["baseline_json"] = data if isinstance(data, dict) else {}
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)

    return {
        "session_id": sid,
        "before": session["baseline_json"],
        "after": session["working_json"],
        "diffs": [],
        "schema_summary": {
            "top_level_keys": list((data if isinstance(data, dict) else {}).keys()),
            "nested_depth": 0,
        },
    }


@app.post("/api/chat")
async def endpoint_chat(
    session_id: str = Form(...),
    message: str = Form(...),
    working_json_str: str | None = Form(default=None),
    _auth=Depends(require_api_key),
):
    """Send a chat turn; stream SSE response (ADR-0004)."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        working_json = (
            _json.loads(working_json_str)
            if working_json_str
            else session["working_json"]
        )
    except (_json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid working_json in request")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # If session has no JSON yet, tell user to upload
            if not working_json:
                yield _sse("thinking", {"text": "No JSON configured yet."})
                yield _sse(
                    "complete",
                    {
                        "working_json": {},
                        "explanation": (
                            "Please upload a JSON configuration first. Use the "
                            "Upload tab to provide your initial JSON, then chat "
                            "to modify it."
                        ),
                    },
                )
                return

            merged_json = None
            all_diffs: list[dict[str, Any]] = []
            async for event_text in _stream_llm(working_json, message, _auth):
                yield event_text
                event, payload = _parse_sse(event_text)
                if event == "complete" and payload is not None:
                    merged_json = payload.get("working_json")
                elif event == "diff" and payload is not None:
                    entry = payload.get("entry")
                    if isinstance(entry, dict):
                        all_diffs.append(entry)

            # Persist the merged working_json to session store.
            if merged_json is not None:
                session["working_json"] = merged_json
                if all_diffs:
                    session.setdefault("conversation_history", []).append(
                        {
                            "role": "assistant",
                            "content": "",
                            "diffs": [
                                {
                                    "path": d.get("path", ""),
                                    "operation": d.get("operation", ""),
                                    "old_value": d.get("old_value"),
                                    "new_value": d.get("new_value"),
                                    "id": str(d.get("id", "")),
                                }
                                for d in all_diffs
                            ],
                        }
                    )
                session["updated_at"] = datetime.now(timezone.utc).isoformat()
                save_session(session)

        except Exception as e:
            logger.exception("chat endpoint stream failed")
            yield _sse(
                "complete",
                {"working_json": working_json, "explanation": f"Error: {e}"},
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Diff accept/reject endpoints
#
# Lifecycle: diffs proposed in a chat turn are already applied to
# working_json (preview state). Accepting a diff promotes it into
# baseline_json; rejecting a diff reverts it from working_json.
# baseline_json is never modified by a reject, and working_json is
# never re-applied on accept (that previously duplicated array
# inserts/deletes).
# ---------------------------------------------------------------------------


def _find_diff_in_history(session: dict[str, Any], diff_id: str) -> dict | None:
    turns = session.get("conversation_history", [])
    for turn in reversed(turns):
        if turn.get("role") == "assistant" and turn.get("diffs"):
            for diff in turn["diffs"]:
                if diff.get("id") == diff_id:
                    return diff
    return None


@app.post("/api/sessions/{session_id}/diffs/accept-all")
async def endpoint_accept_all_diffs(
    session_id: str,
    _auth=Depends(require_api_key),
):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session["baseline_json"] = copy.deepcopy(session["working_json"])
    session["applied_diffs"] = []
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return {
        "working_json": session["working_json"],
        "baseline_json": session["baseline_json"],
        "diffs": [],
    }


@app.post("/api/sessions/{session_id}/diffs/reject-all")
async def endpoint_reject_all_diffs(
    session_id: str,
    _auth=Depends(require_api_key),
):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session["working_json"] = copy.deepcopy(session.get("baseline_json", {}))
    session["applied_diffs"] = []
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return {
        "working_json": session["working_json"],
        "baseline_json": session.get("baseline_json", {}),
        "diffs": [],
    }


@app.post("/api/sessions/{session_id}/diffs/{diff_id}/accept")
async def endpoint_accept_single_diff(
    session_id: str,
    diff_id: str,
    _auth=Depends(require_api_key),
):
    """Accept a single diff by ID: promote it into baseline_json.

    working_json already contains the change (applied during the chat
    stream), so only the baseline needs the diff applied.
    """
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    target = _find_diff_in_history(session, diff_id)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diff with id {diff_id} not found in conversation history",
        )

    try:
        baseline_json = DiffUtils.apply(target, session.get("baseline_json", {}))
    except DiffApplyError as exc:
        raise HTTPException(
            status_code=422, detail=f"Cannot accept diff {diff_id}: {exc}"
        )

    session["baseline_json"] = baseline_json
    session["applied_diffs"] = session.get("applied_diffs", []) + [target.get("id", "")]
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return {
        "success": True,
        "working_json": session.get("working_json", {}),
        "baseline_json": baseline_json,
        "applied_diffs": session["applied_diffs"],
    }


@app.post("/api/sessions/{session_id}/diffs/{diff_id}/reject")
async def endpoint_reject_single_diff(
    session_id: str,
    diff_id: str,
    _auth=Depends(require_api_key),
):
    """Reject a single diff by ID: revert it from working_json.

    baseline_json never contained the change, so it is left untouched.
    """
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    target = _find_diff_in_history(session, diff_id)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diff with id {diff_id} not found in conversation history",
        )

    try:
        working_json = DiffUtils.revert(target, session.get("working_json", {}))
    except DiffApplyError as exc:
        raise HTTPException(
            status_code=422, detail=f"Cannot reject diff {diff_id}: {exc}"
        )

    session["working_json"] = working_json
    session["rejected_diffs"] = session.get("rejected_diffs", []) + [
        target.get("id", "")
    ]
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return {
        "success": True,
        "working_json": working_json,
        "baseline_json": session.get("baseline_json", {}),
        "applied_diffs": session.get("applied_diffs", []),
        "rejected_diffs": session["rejected_diffs"],
    }


@app.post("/api/explain")
async def endpoint_explain(
    body: dict[str, Any],
    _auth=Depends(require_api_key),
):
    """Explain the JSON in a session. Returns markdown as plain text."""
    session_id = body.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId is required")

    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    working_json = body.get("workingJson", session.get("working_json", {}))
    if not isinstance(working_json, dict):
        working_json = {}

    try:
        markdown = await GatewayService.explain(session_id, _auth, working_json)
    except Exception as e:
        logger.exception("explain failed session=%s", session_id)
        raise HTTPException(status_code=500, detail=f"Explain failed: {e}")

    return Response(content=markdown, media_type="text/plain")
