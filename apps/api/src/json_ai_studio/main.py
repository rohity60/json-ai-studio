"""JSON AI Studio -- FastAPI backend.

All 11 endpoints from openapi/spec.yaml. SSE streaming for /api/chat
(ADR-0004). In-memory session store (ADR-0006). Fail-fast errors (ADR-0007).
Uses litellm pointed at local Ollama backend (http://localhost:11434/v1).

Auth: all endpoints protected by X-API-Key header + rate limiter (10 req/min per key).
"""

from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .auth import require_api_key
from .models import (
    ChatRequest,
    ChatTurn,
    CreateSessionRequest,
    CreateVersionRequest,
    DiffAcceptResponse,
    DiffEntry,
    DiffRejectResponse,
    Error,
    ValidateRequest,
    ValidationErrorItem,
    VersionSnapshot,
)
from .store import (
    create_session as _new_session,
    delete_session,
    get_session,
    list_sessions,
    save_session,
)
from .utils import compute_diff as _compute_diff, validate_document

app = FastAPI(title="JSON AI Studio API", version="0.1.0")

# CORS -- handle OPTIONS preflight for fetch with X-API-Key header
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "x-api-key"],
    max_age=86400,
)


# ---------------------------------------------------------------------------
# LiteLLM integration (ADR-0002)
# ---------------------------------------------------------------------------


def _build_system_prompt(working_json: dict[str, Any]) -> str:
    """Build system prompt with working JSON schema summary (not full dump).

    Uses only top-level keys and depth info to keep request body small.
    Full JSON dump caused 5-60s freeze -- Ollama choked on large payloads.
    """
    top_keys = list(working_json.keys()) if isinstance(working_json, dict) else []
    return f"""\
You are a JSON configuration assistant. Given the current working JSON and a user's \
natural language message, return structured diff proposals as a JSON array of DiffEntry objects.

Working JSON schema: {top_keys}

Rules:
- Each DiffEntry has: path (JSON Pointer), operation ("add"|"modify"|"delete"), old_value, new_value
- Only output the JSON array -- nothing else.
- If the user's request cannot be applied, explain why in plain text.

Example 1 - Modify a value:
User: "Increase timeout from 30 to 60 for api service."
Output: [{{"path": "/services/api/timeout", "operation": "modify", "old_value": 30, "new_value": 60}}]

Example 2 - Add a field:
User: "Add retry count of 5."
Output: [{{"path": "/services/default/retryCount", "operation": "add", "old_value": null, "new_value": 5}}]

Now process the user's message and return diffs in this exact format.
"""


# ---------------------------------------------------------------------------
# Schema Summary Helper
# ---------------------------------------------------------------------------


def _compute_schema_summary(data: Any, depth: int = 0) -> dict[str, Any]:
    """Compute schema summary: top-level keys, max nesting depth, array lengths."""
    top_keys: list[str] = []
    max_depth = depth
    array_lengths: dict[str, int] = {}

    if isinstance(data, dict):
        top_keys = list(data.keys())
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                result = _compute_schema_summary(value, depth + 1)
                max_depth = max(max_depth, result["nested_depth"])
                array_lengths.update(result["array_lengths"])
    elif isinstance(data, list):
        max_depth = depth + 1 if data else depth
        array_lengths[f"/[{depth}]"] = len(data)

    return {
        "top_level_keys": top_keys,
        "nested_depth": max(max_depth, 0),
        "array_lengths": array_lengths,
    }


# ---------------------------------------------------------------------------
# Diff Application Helper
# ---------------------------------------------------------------------------


def _apply_diffs(obj: dict[str, Any], diffs: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a list of diff entries to a JSON object (returns new copy)."""
    import copy

    result = copy.deepcopy(obj)
    for diff in diffs:
        path_parts = [p for p in diff.get("path", "/").split("/") if p]
        target_key = path_parts[-1] if path_parts else None
        if not target_key:
            continue
        # Navigate to parent, creating intermediate dicts as needed
        current = result
        for part in path_parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        op = diff.get("operation")
        if op == "delete":
            current.pop(target_key, None)
        else:
            current[target_key] = diff.get("new_value")
    return result


# ---------------------------------------------------------------------------
# SSE Chat Streaming (ADR-0004)
# ---------------------------------------------------------------------------


async def _stream_llm(
    working_json: dict[str, Any], message: str
) -> AsyncGenerator[str, None]:
    """Stream LLM response as SSE events.

    Event sequence: thinking -> diff(s) -> complete (ADR-0004).
    Uses litellm streaming against local Ollama backend (ADR-0002, ADR-0004).
    After collecting diffs, applies them to working_json so the final JSON
    reflects all suggested changes -- even if individual diff new_value is null.
    """
    yield "event: thinking\ndata" + _json.dumps(
        {"text": "Analyzing your request..."}
    ) + "\n\n"
    await asyncio.sleep(0.1)

    try:
        import litellm

        system_prompt = _build_system_prompt(working_json)
        response = await litellm.acompletion(
            model="ollama/qwen3.6:35b-mlx",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            stream=True,
            timeout=120.0,
        )

        content_parts: list[str] = []
        async for chunk in response:
            text = chunk.choices[0].delta.get("content")
            if text:
                content_parts.append(text)
                yield "event: thinking\ndata" + _json.dumps({"text": text}) + "\n\n"

        combined = "".join(content_parts)

        # Try to parse the LLM response as a list of diff entries
        diffs_to_apply: list[dict[str, Any]] = []
        try:
            parsed = _json.loads(combined)
            if isinstance(parsed, list):
                for d in parsed:
                    if isinstance(d, dict) and "path" in d and "operation" in d:
                        diffs_to_apply.append(d)
        except (_json.JSONDecodeError, ValueError):
            pass

        if diffs_to_apply:
            # Emit individual diff events for frontend rendering (with UUIDs)
            diff_entries_with_ids = []
            for diff in diffs_to_apply:
                entry = {**diff, "id": str(uuid4())}  # inject id
                diff_entries_with_ids.append(entry)
                yield "event: diff\ndata" + _json.dumps({"entry": entry}) + "\n\n"
            yield "event: complete\ndata" + _json.dumps(
                {
                    "working_json": _apply_diffs(working_json, diffs_to_apply),
                    "explanation": combined,
                }
            ) + "\n\n"
            return

        # No structured diffs -- emit a generic one and the unchanged JSON
        yield "event: diff\ndata" + _json.dumps(
            {
                "path": "/last_change",
                "operation": "modify",
                "old_value": None,
                "new_value": message,
            }
        ) + "\n\n"
        yield "event: complete\ndata" + _json.dumps(
            {
                "working_json": working_json,
                "explanation": combined,
            }
        ) + "\n\n"

    except Exception as e:
        # Fail-fast error (ADR-0007): yield error in stream, don't retry
        yield "event: complete\ndata" + _json.dumps(
            {
                "working_json": working_json,
                "explanation": f"Error: {e}",
            }
        ) + "\n\n"


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
            "validate": "POST /api/validate",
            "diff": "POST /api/diff",
            "versions_get": "GET /api/sessions/{id}/versions",
            "versions_post": "POST /api/sessions/{id}/versions",
            "diff_accept": "POST /api/sessions/{id}/diffs/{diffId}/accept",
            "diff_reject": "POST /api/sessions/{id}/diffs/{diffId}/reject",
            "export": "GET /api/sessions/{id}/export",
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
            v.model_dump() if hasattr(v, "model_dump") else v
            for v in versions
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
            merged_json = None
            all_diffs: list[dict[str, Any]] = []
            async for event_text in _stream_llm(working_json, message):
                yield event_text
                # Capture working_json from the "complete" event payload
                if event_text.startswith("event: complete"):
                    try:
                        parts = event_text.split("\n", 1)
                        if len(parts) > 1:
                            data_str = parts[1].lstrip("data").strip()
                            complete_data = _json.loads(data_str)
                            merged_json = complete_data.get("working_json")
                    except (_json.JSONDecodeError, ValueError):
                        pass
                # Collect LLM-injected diff entries for conversation_history
                elif event_text.startswith("event: diff"):
                    try:
                        parts = event_text.split("\n", 1)
                        if len(parts) > 1:
                            data_str = parts[1].lstrip("data").strip()
                            parsed = _json.loads(data_str)
                            entry = parsed.get("entry")
                            if isinstance(entry, dict):
                                all_diffs.append(entry)
                    except (_json.JSONDecodeError, ValueError):
                        pass

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
            yield "event: complete\ndata" + _json.dumps(
                {
                    "working_json": working_json,
                    "explanation": f"Error: {e}",
                }
            ) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Diff accept/reject endpoints
# ---------------------------------------------------------------------------


@app.post("/api/sessions/{session_id}/diffs/accept-all")
async def endpoint_accept_all_diffs(
    session_id: str,
    _auth=Depends(require_api_key),
):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    import copy

    session["baseline_json"] = copy.deepcopy(session["working_json"])
    session["working_json"] = copy.deepcopy(session["baseline_json"])
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
    import copy

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
    """Accept a single diff by ID. Re-applies that specific diff to working_json."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Find the diff in conversation history
    target = None
    turns = session.get("conversation_history", [])
    for turn in reversed(turns):
        if turn.get("role") == "assistant" and turn.get("diffs"):
            for diff in turn["diffs"]:
                if diff.get("id") == diff_id:
                    target = diff
                    break
        if target:
            break

    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diff with id {diff_id} not found in conversation history",
        )

    import copy

    current_json = copy.deepcopy(session.get("working_json", {}))
    # Re-apply this diff on top of current state
    path_parts = [p for p in target.get("path", "/").split("/") if p]
    target_key = path_parts[-1] if path_parts else None
    if target_key:
        current = current_json
        for part in path_parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                break
            current = current[part]
        else:
            if target.get("operation") == "delete":
                current.pop(target_key, None)
            else:
                current[target_key] = target.get("new_value")

    session["working_json"] = current_json
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    session["applied_diffs"] = session.get("applied_diffs", []) + [target.get("id", "")]
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return {
        "success": True,
        "working_json": current_json,
        "baseline_json": session.get("baseline_json", {}),
        "applied_diffs": session.get("applied_diffs", []),
    }


@app.post("/api/sessions/{session_id}/diffs/{diff_id}/reject")
async def endpoint_reject_single_diff(
    session_id: str,
    diff_id: str,
    _auth=Depends(require_api_key),
):
    """Reject a single diff by ID. Reverses that specific diff."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    target = None
    turns = session.get("conversation_history", [])
    for turn in reversed(turns):
        if turn.get("role") == "assistant" and turn.get("diffs"):
            for diff in turn["diffs"]:
                if diff.get("id") == diff_id:
                    target = diff
                    break
        if target:
            break

    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diff with id {diff_id} not found in conversation history",
        )

    import copy

    current_json = copy.deepcopy(session.get("working_json", {}))
    path_parts = [p for p in target.get("path", "/").split("/") if p]
    target_key = path_parts[-1] if path_parts else None
    if target_key:
        current = current_json
        for part in path_parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                break
            current = current[part]
        else:
            op = target.get("operation")
            if op == "add":
                current.pop(target_key, None)
            elif op == "modify" and "old_value" in target:
                current[target_key] = target["old_value"]
            elif op == "delete" and "old_value" in target:
                current[target_key] = target["old_value"]

    session["working_json"] = current_json
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    return {
        "success": True,
        "working_json": current_json,
        "baseline_json": session.get("baseline_json", {}),
        "applied_diffs": session.get("applied_diffs", []),
    }
