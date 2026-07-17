"""SSE chat streaming (ADR-0004): LLM call, diff parsing, session persistence.

Moved verbatim from main.py during the layered restructure (ADR-0013).
Event sequence: thinking -> diff(s) -> complete.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any, AsyncGenerator
from uuid import uuid4

from ..db.session_store import store
from ..diff_utils import DiffUtils, parse_llm_response
from ..gateway import GatewayService
from ..prompting import build_system_prompt
from .session_service import now_iso

logger = logging.getLogger("json_ai_studio.chat")


def sse(event: str, payload: dict[str, Any]) -> str:
    """Format one spec-compliant SSE event block."""
    return f"event: {event}\ndata: {_json.dumps(payload)}\n\n"


def parse_sse(event_text: str) -> tuple[str | None, dict[str, Any] | None]:
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


async def _stream_llm(
    session_id: str, working_json: dict[str, Any], message: str, principal
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
        logger.info(
            "chat turn start session=%s message_len=%d working_keys=%d user_message=%r",
            session_id,
            len(message),
            len(working_json),
            message[:500],
        )
        logger.debug(
            "chat turn full session=%s message=%r working_json=%s",
            session_id,
            message,
            working_json,
        )
        yield sse("thinking", {"text": "Analyzing your request..."})

        system_prompt = build_system_prompt(working_json)
        logger.debug(
            "chat system_prompt session=%s prompt=%s", session_id, system_prompt
        )

        content_parts: list[str] = []
        error_payload: dict[str, Any] | None = None
        quota_hit = False
        async for event_text in GatewayService.invoke(
            session_id, message, principal, system_prompt
        ):
            yield event_text
            event, payload = parse_sse(event_text)
            if event == "thinking" and payload is not None:
                text = payload.get("text")
                if isinstance(text, str):
                    content_parts.append(text)
            elif event == "error" and payload is not None:
                error_payload = payload
            elif event in ("rate_limit", "credit_limit", "service_unavailable"):
                quota_hit = True

        # The rate_limit/credit_limit/service_unavailable event was already
        # forwarded to the client (it becomes a popup); stop here so we don't
        # emit a misleading "complete" with an empty explanation.
        if quota_hit:
            return

        combined = "".join(content_parts)
        logger.info("chat stream finished response_len=%d", len(combined))
        logger.debug("llm raw output (full) session=%s: %s", session_id, combined)

        if error_payload is not None:
            yield sse(
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
        logger.debug(
            "parsed llm response (full) session=%s diffs=%s explanation=%r",
            session_id,
            diffs,
            explanation,
        )

        if not diffs:
            logger.warning(
                "no diffs parsed from llm output (len=%d); "
                "returning explanation only",
                len(combined),
            )
            yield sse(
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
        logger.debug(
            "diff application (full) session=%s applied=%s failed=%s merged=%s",
            session_id,
            applied,
            failed,
            merged,
        )

        for diff in applied:
            entry = {**diff, "id": str(uuid4())}
            yield sse("diff", {"entry": entry})

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
        yield sse(
            "complete",
            {
                "working_json": merged,
                "explanation": " ".join(notes) or "Done.",
            },
        )

    except Exception as e:
        # Fail-fast error (ADR-0007): yield error in stream, don't retry
        logger.exception("chat stream failed")
        yield sse(
            "complete",
            {"working_json": working_json, "explanation": f"Error: {e}"},
        )


async def chat_event_stream(
    session: dict[str, Any],
    working_json: dict[str, Any],
    message: str,
    principal,
) -> AsyncGenerator[str, None]:
    """Full chat turn: stream LLM events, then persist the merged JSON."""
    try:
        # If session has no JSON yet, tell user to upload
        if not working_json:
            yield sse("thinking", {"text": "No JSON configured yet."})
            yield sse(
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
        async for event_text in _stream_llm(
            session.get("id", "chat-session"), working_json, message, principal
        ):
            yield event_text
            event, payload = parse_sse(event_text)
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
            session["updated_at"] = now_iso()
            await store.save_session(session)
            logger.info(
                "chat turn persisted session=%s diffs=%d",
                session.get("id"),
                len(all_diffs),
            )
            logger.debug(
                "chat turn merged_json session=%s json=%s",
                session.get("id"),
                merged_json,
            )

    except Exception as e:
        logger.exception("chat endpoint stream failed")
        yield sse(
            "complete",
            {"working_json": working_json, "explanation": f"Error: {e}"},
        )
