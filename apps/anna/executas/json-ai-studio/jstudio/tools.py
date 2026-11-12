"""Tool handlers: thin adapters from Anna tool calls to the shared services.

Every handler returns the payload for ``{"success": True, "data": …}``;
``ToolError`` becomes ``{"success": False, "error": …}``. No business
logic lives here — it is all in ``json_ai_studio.services``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from . import wiring  # noqa: F401  (must configure the engine first)

from json_ai_studio.gateway import GatewayService
from json_ai_studio.models import RestoreVersionsRequest
from json_ai_studio.services import (
    chat_history_service,
    chat_service,
    deployment_budget,
    diff_service,
    session_service,
    version_service,
)
from json_ai_studio.services.errors import ConflictError, NotFoundError

from . import anna_llm
from .rpc import current_invoke_id, host

logger = logging.getLogger("jstudio.tools")

# Async job results are capped at 256 KB by the host; keep clear of it.
MAX_RESULT_BYTES = 200 * 1024

OUT_OF_CREDITS = (
    "Your Anna credits are used up, so the model could not run. "
    "Top up or wait for your quota to reset, then try again."
)
TURN_TOO_BIG = (
    "This request needed more model usage than Anna allows for one run. "
    "Try a smaller change or focus on one section of the document."
)


class ToolError(Exception):
    """Expected failure with a message safe to show the user."""


def _str(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"'{name}' is required")
    return value


def _doc(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ToolError(f"Not valid JSON: {exc.msg} (line {exc.lineno})") from exc
    if not isinstance(value, dict):
        raise ToolError("The document must be a JSON object")
    return value


def _host_failure() -> str | None:
    """User-facing reason when the last sampling call was refused by Anna."""
    err = anna_llm.take_last_error(current_invoke_id())
    if err is None:
        return None
    if err.code == anna_llm.QUOTA_EXCEEDED:
        return OUT_OF_CREDITS
    if err.code in (anna_llm.MAX_CALLS_EXCEEDED, anna_llm.MAX_TOKENS_EXCEEDED):
        return TURN_TOO_BIG
    return None


def _session_view(session: dict[str, Any]) -> dict[str, Any]:
    """Session as JSON for the UI (version snapshots may be pydantic)."""
    from .aps_store import _dumps

    return json.loads(_dumps(session))


# --- documents ---------------------------------------------------------------


async def list_docs(args: dict[str, Any]) -> dict[str, Any]:
    return {"docs": await wiring.store().list_summaries()}


async def create_session(args: dict[str, Any]) -> dict[str, Any]:
    """Empty document, as the web app's POST /api/sessions."""
    session = await session_service.create_session(args.get("name") or "Untitled")
    return _session_view(session)


async def upload_json(args: dict[str, Any]) -> dict[str, Any]:
    """Load a JSON document into a session (new one when none is given)."""
    return await session_service.upload_json(
        _doc(args.get("json")), args.get("session_id") or None
    )


async def create_doc(args: dict[str, Any]) -> dict[str, Any]:
    data = _doc(args.get("json"))
    session = await session_service.create_session(args.get("name") or "Untitled")
    result = await session_service.upload_json(data, session["id"])
    return {"session_id": result["session_id"]}


async def get_doc(args: dict[str, Any]) -> dict[str, Any]:
    session = await session_service.get_session(_str(args, "session_id"))
    return _session_view(session)


async def delete_doc(args: dict[str, Any]) -> dict[str, Any]:
    return {"deleted": await wiring.store().delete_session(_str(args, "session_id"))}


# --- chat ----------------------------------------------------------------------


async def chat_turn(args: dict[str, Any]) -> dict[str, Any]:
    """One chat turn. Returns the same events the web app streams as SSE."""
    session = await session_service.get_session(_str(args, "session_id"))
    message = _str(args, "message")
    # Anna's cap is per invoke, not per minute: start each turn clean.
    deployment_budget.reset()

    events: list[dict[str, Any]] = []
    async for event_text in chat_service.chat_event_stream(
        session,
        session["working_json"],
        message,
        wiring.PRINCIPAL,
        thinking=bool(args.get("thinking")),
        focus_path=args.get("focus_path") or None,
    ):
        event, payload = chat_service.parse_sse(event_text)
        if event is None or payload is None or event == "thinking":
            continue  # the raw model text is not part of the result
        events.append({"event": event, "data": payload})
        if event not in ("complete", "diff"):
            host.progress({"event": event, "data": payload})

    failure = _host_failure()
    if failure:
        for item in events:
            if item["event"] == "complete":
                item["data"]["explanation"] = failure
        events.append({"event": "host_error", "data": {"message": failure}})

    result = {"events": events}
    if len(json.dumps(result, default=str).encode("utf-8")) > MAX_RESULT_BYTES:
        # Too big for a job result: the UI reloads the document with get_doc.
        for item in events:
            if item["event"] == "complete":
                item["data"].pop("working_json", None)
                item["data"]["working_json_omitted"] = True
    return result


async def explain(args: dict[str, Any]) -> dict[str, Any]:
    session = await session_service.get_session(_str(args, "session_id"))
    deployment_budget.reset()
    try:
        markdown = await GatewayService.explain(
            session["id"], wiring.PRINCIPAL, session.get("working_json") or {}
        )
    except Exception as exc:
        logger.exception("explain failed session=%s", session["id"])
        raise ToolError(
            _host_failure() or "The model could not explain this document right now."
        ) from exc
    return {"markdown": markdown}


async def clear_chat(args: dict[str, Any]) -> dict[str, Any]:
    await chat_history_service.clear_chat(_str(args, "session_id"))
    return {"cleared": True}


# --- diffs ---------------------------------------------------------------------


async def accept_diff(args: dict[str, Any]) -> dict[str, Any]:
    return await diff_service.accept_one(
        _str(args, "session_id"), _str(args, "diff_id")
    )


async def reject_diff(args: dict[str, Any]) -> dict[str, Any]:
    return await diff_service.reject_one(
        _str(args, "session_id"), _str(args, "diff_id")
    )


async def accept_all(args: dict[str, Any]) -> dict[str, Any]:
    return await diff_service.accept_all(_str(args, "session_id"))


async def reject_all(args: dict[str, Any]) -> dict[str, Any]:
    return await diff_service.reject_all(_str(args, "session_id"))


# --- versions ------------------------------------------------------------------


async def save_version(args: dict[str, Any]) -> dict[str, Any]:
    session = await session_service.get_session(_str(args, "session_id"))
    data = args.get("json")
    version = await version_service.create_snapshot(
        session["id"],
        args.get("label") or "Snapshot",
        _doc(data) if data is not None else session["working_json"],
    )
    return json.loads(json.dumps(version, default=str))


async def list_versions(args: dict[str, Any]) -> dict[str, Any]:
    result = await version_service.list_versions(_str(args, "session_id"))
    return json.loads(json.dumps(result, default=str))


async def select_version(args: dict[str, Any]) -> dict[str, Any]:
    result = await version_service.select_version(
        _str(args, "session_id"), _str(args, "version_id")
    )
    return json.loads(json.dumps(result, default=str))


async def restore_versions(args: dict[str, Any]) -> dict[str, Any]:
    """Refill an empty session from the browser's cached copy (ADR-0014)."""
    payload = args.get("payload")
    if not isinstance(payload, dict):
        raise ToolError("'payload' is required")
    session = await version_service.restore_versions(
        _str(args, "session_id"), RestoreVersionsRequest(**payload)
    )
    return _session_view(session)


# --- registry ------------------------------------------------------------------

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _p(
    name: str, type_: str, description: str, required: bool = True
) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_,
        "description": description,
        "required": required,
    }


_SID = _p("session_id", "string", "Document id from create_doc or list_docs.")

TOOLS: dict[str, tuple[Handler, str, list[dict[str, Any]]]] = {
    "list_docs": (list_docs, "List the user's saved JSON documents.", []),
    "create_session": (
        create_session,
        "Create an empty document.",
        [_p("name", "string", "Display name.", required=False)],
    ),
    "upload_json": (
        upload_json,
        "Load a JSON object into a document, replacing its content.",
        [
            _p("json", "object", "The JSON document."),
            _p(
                "session_id",
                "string",
                "Document to load into; omit for a new one.",
                required=False,
            ),
        ],
    ),
    "create_doc": (
        create_doc,
        "Create a document from a JSON object (or JSON text).",
        [
            _p("json", "object", "The JSON document."),
            _p("name", "string", "Display name.", required=False),
        ],
    ),
    "get_doc": (
        get_doc,
        "Get a document: working JSON, versions, chat history.",
        [_SID],
    ),
    "delete_doc": (delete_doc, "Delete a document and its history.", [_SID]),
    "chat_turn": (
        chat_turn,
        "Apply a natural-language edit request; returns reviewable diffs.",
        [
            _SID,
            _p("message", "string", "What to change, in plain language."),
            _p("thinking", "boolean", "Use deeper reasoning.", required=False),
            _p(
                "focus_path",
                "string",
                "JSON Pointer of the section to work on.",
                required=False,
            ),
        ],
    ),
    "explain": (explain, "Explain the document in markdown.", [_SID]),
    "clear_chat": (clear_chat, "Clear the chat history of a document.", [_SID]),
    "accept_diff": (
        accept_diff,
        "Keep one proposed change.",
        [_SID, _p("diff_id", "string", "Id of the change.")],
    ),
    "reject_diff": (
        reject_diff,
        "Undo one proposed change.",
        [_SID, _p("diff_id", "string", "Id of the change.")],
    ),
    "accept_all": (accept_all, "Keep every pending change.", [_SID]),
    "reject_all": (reject_all, "Undo every pending change.", [_SID]),
    "save_version": (
        save_version,
        "Save the current JSON as a named version.",
        [
            _SID,
            _p("label", "string", "Version label.", required=False),
            _p(
                "json",
                "object",
                "JSON to snapshot; defaults to the working JSON.",
                required=False,
            ),
        ],
    ),
    "restore_versions": (
        restore_versions,
        "Restore cached versions into an empty document.",
        [_SID, _p("payload", "object", "Cached versions, working JSON and chat.")],
    ),
    "list_versions": (list_versions, "List saved versions.", [_SID]),
    "select_version": (
        select_version,
        "Load a saved version as the working JSON.",
        [_SID, _p("version_id", "string", "Id of the version.")],
    ),
}


def manifest_tools() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": description, "parameters": parameters}
        for name, (_handler, description, parameters) in TOOLS.items()
    ]


async def run(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one tool and wrap the outcome in the host's result envelope."""
    entry = TOOLS.get(tool)
    if entry is None:
        return {"success": False, "error": f"unknown tool: {tool}"}
    try:
        return {"success": True, "data": await entry[0](args or {})}
    except NotFoundError as exc:
        # The UI reuses the web app's client logic, which branches on HTTP
        # status: carry the equivalent as a prefix.
        return {"success": False, "error": f"404: {exc}"}
    except ConflictError as exc:
        return {"success": False, "error": f"409: {exc}"}
    except ToolError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        # Never leak internals to the UI; the traceback goes to stderr.
        logger.exception("tool %s failed", tool)
        return {"success": False, "error": "Something went wrong. Please try again."}
