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
    job_service,
    deployment_budget,
    diff_service,
    session_service,
    version_service,
)
from json_ai_studio.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
)

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

    return await _collect(
        chat_service.chat_event_stream(
            session,
            session["working_json"],
            message,
            wiring.PRINCIPAL,
            thinking=bool(args.get("thinking")),
            focus_path=args.get("focus_path") or None,
        ),
        outcomes=("complete", "diff"),
    )


async def _collect(
    stream, outcomes: tuple[str, ...], drop: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Run an SSE event stream to the end. Outcome events go in the result;
    the rest are relayed live as job progress. ``drop`` events are skipped
    (the client gets the same data elsewhere)."""
    events: list[dict[str, Any]] = []
    async for event_text in stream:
        event, payload = chat_service.parse_sse(event_text)
        if event is None or payload is None or event == "thinking" or event in drop:
            continue  # the raw model text is not part of the result
        events.append({"event": event, "data": payload})
        if event not in outcomes:
            host.progress({"event": event, "data": payload})

    failure = _host_failure()
    if failure:
        for item in events:
            if item["event"] == "complete":
                item["data"]["explanation"] = failure
        events.append({"event": "host_error", "data": {"message": failure}})
    return _fit_result({"events": events})


def _size(value: Any) -> int:
    return len(json.dumps(value, default=str).encode("utf-8"))


def _fit_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep a job result under the host's cap, dropping what the client can
    fetch again: first the document (the UI reloads it with get_doc), then
    the copy of the diffs a batch also carries in its chat turn."""
    if _size(result) <= MAX_RESULT_BYTES:
        return result
    for item in result["events"]:
        if item["event"] in ("complete", "batch_complete"):
            item["data"].pop("working_json", None)
            item["data"].pop("baseline_json", None)
            item["data"]["working_json_omitted"] = True
    if _size(result) <= MAX_RESULT_BYTES:
        return result
    for item in result["events"]:
        if item["event"] == "batch_complete" and item["data"].get("turn"):
            item["data"].pop("diffs", None)
    if _size(result) > MAX_RESULT_BYTES:
        logger.warning("job result still %d bytes after trimming", _size(result))
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


def _batch_filter(args: dict[str, Any]) -> dict[str, Any]:
    """Optional narrowing to one review job, or one of its batches."""
    job_id = args.get("job_id")
    if not job_id:
        return {}
    batch_no = args.get("batch_no")
    return {"job_id": job_id, "batch_no": int(batch_no) if batch_no else None}


async def accept_all(args: dict[str, Any]) -> dict[str, Any]:
    return await diff_service.accept_all(
        _str(args, "session_id"), **_batch_filter(args)
    )


async def reject_all(args: dict[str, Any]) -> dict[str, Any]:
    return await diff_service.reject_all(
        _str(args, "session_id"), **_batch_filter(args)
    )


# --- whole-document review jobs (ADR-0026) ---------------------------------------


class JobConflict(Exception):
    """409 with the structured detail the web client reads."""

    def __init__(self, detail: dict[str, Any]) -> None:
        super().__init__(detail.get("error", "conflict"))
        self.detail = detail


async def create_job(args: dict[str, Any]) -> dict[str, Any]:
    try:
        return await job_service.create_job(
            _str(args, "session_id"),
            args.get("scope_path") or None,
            _str(args, "instruction"),
            args.get("source_turn_id") or None,
        )
    except ConflictError as exc:
        raise JobConflict({"error": "job_active", "job_id": str(exc)}) from exc
    except InvalidInputError as exc:
        raise ToolError(str(exc)) from exc


async def get_job(args: dict[str, Any]) -> dict[str, Any]:
    return await job_service.get_job(_str(args, "session_id"), _str(args, "job_id"))


async def cancel_job(args: dict[str, Any]) -> dict[str, Any]:
    try:
        return await job_service.cancel_job(
            _str(args, "session_id"), _str(args, "job_id")
        )
    except ConflictError as exc:
        raise JobConflict({"error": str(exc)}) from exc


async def next_batch(args: dict[str, Any]) -> dict[str, Any]:
    """Process exactly one batch of a review job; one LLM call."""
    try:
        session, job = await job_service.begin_next(
            _str(args, "session_id"), _str(args, "job_id")
        )
    except ConflictError as exc:
        raise JobConflict({"error": str(exc)}) from exc
    deployment_budget.reset()
    # The UI reads a batch from batch_complete (its chat turn carries the
    # diffs); the per-diff events would only double the result size.
    return await _collect(
        job_service.run_batch(session, job, wiring.PRINCIPAL),
        outcomes=("batch_complete", "batch_failed"),
        drop=("diff",),
    )


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
_JOB = _p("job_id", "string", "Review job id.")
_JOB_OPT = _p("job_id", "string", "Only this review job's changes.", required=False)
_BATCH_OPT = _p("batch_no", "integer", "Only this batch of the job.", required=False)

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
    "accept_all": (
        accept_all,
        "Keep every pending change (optionally one review job / batch).",
        [_SID, _JOB_OPT, _BATCH_OPT],
    ),
    "reject_all": (
        reject_all,
        "Undo every pending change (optionally one review job / batch).",
        [_SID, _JOB_OPT, _BATCH_OPT],
    ),
    "create_job": (
        create_job,
        "Start a whole-document review job.",
        [
            _SID,
            _p("instruction", "string", "What to check or change across the document."),
            _p(
                "scope_path",
                "string",
                "JSON Pointer to review; omit for the whole document.",
                required=False,
            ),
            _p(
                "source_turn_id",
                "string",
                "Chat turn that proposed the review.",
                required=False,
            ),
        ],
    ),
    "get_job": (get_job, "Get a review job's progress.", [_SID, _JOB]),
    "cancel_job": (cancel_job, "Cancel a review job.", [_SID, _JOB]),
    "next_batch": (next_batch, "Run the next batch of a review job.", [_SID, _JOB]),
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
    except JobConflict as exc:
        return {"success": False, "error": "409: " + json.dumps(exc.detail)}
    except ConflictError as exc:
        return {"success": False, "error": f"409: {exc}"}
    except ToolError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        # Never leak internals to the UI; the traceback goes to stderr.
        logger.exception("tool %s failed", tool)
        return {"success": False, "error": "Something went wrong. Please try again."}
