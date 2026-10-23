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
from ..bulk_edits import expand_all, extract_bulk, extract_question
from ..diff_utils import DiffApplyError, DiffUtils, _split_path, parse_llm_response
from ..settings import get_settings
from ..gateway import GatewayService
from ..json_tools import JsonToolbox
from ..prompting import build_system_prompt, is_skeleton_mode
from . import chat_history_service
from .session_service import now_iso

logger = logging.getLogger("json_ai_studio.chat")


def sse(event: str, payload: dict[str, Any]) -> str:
    """Format one spec-compliant SSE event block."""
    return f"event: {event}\ndata: {_json.dumps(payload)}\n\n"


_MISSING = object()


def _value_at(doc: Any, path: str) -> Any:
    """Value at a JSON Pointer, or _MISSING if it does not resolve."""
    try:
        parts = _split_path(path)
    except DiffApplyError:
        return _MISSING
    current = doc
    for part in parts:
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _is_noop(diff: dict[str, Any], doc: Any) -> bool:
    """A modify whose new_value equals the document's current value."""
    if diff.get("operation") != "modify" or not diff.get("path"):
        return False
    current = _value_at(doc, diff["path"])
    return current is not _MISSING and current == diff.get("new_value")


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


def _short(value: Any, limit: int = 120) -> str:
    """Compact repr for logging a diff value — truncated so a large
    new_value (e.g. an embedded object) doesn't flood the log line."""
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


async def _stream_llm(
    session_id: str,
    working_json: dict[str, Any],
    message: str,
    principal,
    reasoning: str | None = None,
    history: list[dict[str, str]] | None = None,
    outcome: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream LLM response as SSE events via GatewayService.

    `history` is replayed prior turns (chat history). `outcome`, when given,
    is filled with what the turn produced (applied/failed diffs,
    explanation) so the caller can persist it without re-parsing SSE; it is
    left with ``store=False`` when the turn should not be recorded (quota
    stop, provider error, exception).

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

        if outcome is None:
            outcome = {}
        outcome["store"] = False
        system_prompt = build_system_prompt(working_json, has_history=bool(history))
        logger.debug(
            "chat system_prompt session=%s prompt=%s", session_id, system_prompt
        )
        logger.debug("chat history session=%s messages=%s", session_id, history)

        content_parts: list[str] = []
        error_payload: dict[str, Any] | None = None
        quota_hit = False
        # Lookup tools only when the model sees a skeleton (ADR-0024);
        # inline documents keep the single streaming call.
        toolbox = (
            JsonToolbox(working_json, get_settings().chat_tool_result_max_chars)
            if is_skeleton_mode(working_json)
            else None
        )
        async for event_text in GatewayService.invoke(
            session_id,
            message,
            principal,
            system_prompt,
            reasoning=reasoning,
            history=history,
            toolbox=toolbox,
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
        # Bulk ops (pattern + where) are expanded server-side against the
        # full document into ordinary diffs — the model may only have seen a
        # skeleton, and listing hundreds of diffs would blow the output cap.
        bulk_ops, bulk_explanation = extract_bulk(combined)
        # Clarifying question with options (ADR-0024); rendered as buttons.
        question = extract_question(combined)
        if question:
            outcome["question"] = question
        bulk_notes: list[str] = []
        if bulk_ops:
            bulk_diffs, bulk_notes = expand_all(
                bulk_ops, working_json, get_settings().bulk_max_matches
            )
            listed = {d.get("path") for d in diffs}
            diffs = [*diffs, *(d for d in bulk_diffs if d["path"] not in listed)]
            explanation = bulk_explanation or explanation
            outcome["bulk"] = bulk_ops
            logger.info(
                "bulk ops=%d expanded_diffs=%d notes=%s",
                len(bulk_ops),
                len(bulk_diffs),
                bulk_notes,
            )
            logger.debug("bulk ops (full) session=%s ops=%s", session_id, bulk_ops)
        logger.info(
            "parsed llm response: diffs=%d explanation=%r",
            len(diffs),
            explanation[:300],
        )
        # Log each generated diff at INFO (not just DEBUG) so failures to
        # apply can be diagnosed from the standard log without flipping to
        # DEBUG. old/new values are truncated to keep lines readable.
        for i, d in enumerate(diffs):
            logger.info(
                "  diff[%d] op=%s path=%s old=%s new=%s",
                i,
                d.get("operation"),
                d.get("path"),
                _short(d.get("old_value")),
                _short(d.get("new_value")),
            )
        logger.debug(
            "parsed llm response (full) session=%s diffs=%s explanation=%r",
            session_id,
            diffs,
            explanation,
        )

        outcome.update(store=True, applied=[], failed=[])
        # Drop modifies that set a value to what it already is (prod: the
        # model re-emitted an unchanged "ip", which reads as "nothing changed").
        kept = [d for d in diffs if not _is_noop(d, working_json)]
        if len(kept) < len(diffs):
            logger.info("dropped no-op diffs=%d", len(diffs) - len(kept))
        diffs = kept
        if not diffs and bulk_notes:
            # The model claimed a bulk change but nothing matched / it was
            # rejected — report that, not the model's optimistic sentence.
            explanation = " ".join(bulk_notes)
        if not diffs:
            outcome["explanation"] = explanation or "The model returned no changes."
            logger.warning(
                "no diffs parsed from llm output (len=%d); "
                "returning explanation only",
                len(combined),
            )
            yield sse(
                "complete",
                {
                    "working_json": working_json,
                    # Never fall back to `combined` (raw model output): a
                    # truncated/malformed diff payload would leak as the
                    # explanation. parse_llm_response returns prose or a
                    # friendly message; "" only for a genuinely empty parse.
                    "explanation": explanation or "The model returned no changes.",
                    **({"question": question} if question else {}),
                },
            )
            return

        merged, applied, failed = DiffUtils.apply_all_verbose(diffs, working_json)
        logger.info("diff application: applied=%d failed=%d", len(applied), len(failed))
        # Per-failed-diff path + reason at INFO — the key signal for "model
        # produced N diffs but none applied" (usually a path that does not
        # resolve against the current working JSON).
        for d, reason in failed:
            logger.info(
                "  FAILED op=%s path=%s reason=%s",
                d.get("operation"),
                d.get("path"),
                reason,
            )
        logger.debug(
            "diff application (full) session=%s applied=%s failed=%s merged=%s",
            session_id,
            applied,
            failed,
            merged,
        )

        applied_entries = [
            {**diff, "id": str(uuid4()), "status": "pending"} for diff in applied
        ]
        for entry in applied_entries:
            yield sse("diff", {"entry": entry})
        outcome["applied"] = applied_entries
        outcome["failed"] = [
            {**diff, "id": str(uuid4()), "status": "failed", "failure_reason": reason}
            for diff, reason in failed
        ]

        notes: list[str] = []
        if explanation:
            notes.append(explanation)
        elif applied:
            notes.append(f"Applied {len(applied)} change(s).")
        notes.extend(bulk_notes)
        if failed:
            failed_desc = "; ".join(
                f"{d.get('path')} ({reason})" for d, reason in failed
            )
            notes.append(
                f"Skipped {len(failed)} proposed change(s) that did not match "
                f"the current JSON: {failed_desc}."
            )
        outcome["explanation"] = " ".join(notes) or "Done."
        yield sse(
            "complete",
            {
                "working_json": merged,
                "explanation": outcome["explanation"],
                **({"question": question} if question else {}),
            },
        )

    except Exception as e:
        # Fail-fast error (ADR-0007): yield error in stream, don't retry
        logger.exception("chat stream failed")
        if outcome is not None:
            outcome["store"] = False
        yield sse(
            "complete",
            {"working_json": working_json, "explanation": f"Error: {e}"},
        )


async def chat_event_stream(
    session: dict[str, Any],
    working_json: dict[str, Any],
    message: str,
    principal,
    thinking: bool = False,
) -> AsyncGenerator[str, None]:
    """Full chat turn: stream LLM events, then persist the merged JSON.

    `thinking` is the UI on/off switch: True elevates the model to high
    reasoning; False uses the deployment default (backends that don't
    support a thinking override ignore this either way).
    """
    # Map the boolean switch onto a generic reasoning level. None = no
    # override (deployment default); "high" = maximum reasoning.
    reasoning = "high" if thinking else None
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

        history = chat_history_service.build_history_messages(session)
        outcome: dict[str, Any] = {}
        async for event_text in _stream_llm(
            session.get("id", "chat-session"),
            working_json,
            message,
            principal,
            reasoning=reasoning,
            history=history,
            outcome=outcome,
        ):
            event, payload = parse_sse(event_text)
            if event != "complete" or payload is None:
                yield event_text
                continue

            # Persist before the client sees "complete" so an immediate
            # accept/reject finds the diff ids in history.
            merged_json = payload.get("working_json")
            if merged_json is not None:
                session["working_json"] = merged_json
            if outcome.get("store"):
                user_turn = chat_history_service.make_turn("user", message)
                assistant_turn = chat_history_service.make_turn(
                    "assistant",
                    outcome.get("explanation", ""),
                    diffs=[
                        *outcome.get("applied", []),
                        *outcome.get("failed", []),
                    ],
                )
                if outcome.get("bulk"):
                    # Replayed instead of the (possibly hundreds of) expanded
                    # diffs' detail, so follow-ups see the intent.
                    assistant_turn["bulk"] = outcome["bulk"]
                if outcome.get("question"):
                    assistant_turn["question"] = outcome["question"]
                chat_history_service.append_turns(session, user_turn, assistant_turn)
                payload["user_turn_id"] = user_turn["id"]
                payload["assistant_turn_id"] = assistant_turn["id"]
            session["updated_at"] = now_iso()
            await store.save_session(session)
            logger.info(
                "chat turn persisted session=%s applied=%d failed=%d stored=%s",
                session.get("id"),
                len(outcome.get("applied", [])),
                len(outcome.get("failed", [])),
                bool(outcome.get("store")),
            )
            logger.debug(
                "chat turn merged_json session=%s json=%s",
                session.get("id"),
                merged_json,
            )
            yield sse("complete", payload)

    except Exception as e:
        logger.exception("chat endpoint stream failed")
        yield sse(
            "complete",
            {"working_json": working_json, "explanation": f"Error: {e}"},
        )
