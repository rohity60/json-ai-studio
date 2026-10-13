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
from ..bulk_edits import expand_all, extract_bulk
from ..diff_utils import DiffUtils, parse_llm_response
from ..settings import get_settings
from ..gateway import GatewayService
from ..prompting import build_system_prompt
from . import chat_history_service
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
        async for event_text in GatewayService.invoke(
            session_id,
            message,
            principal,
            system_prompt,
            reasoning=reasoning,
            history=history,
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
        logger.debug(
            "parsed llm response (full) session=%s diffs=%s explanation=%r",
            session_id,
            diffs,
            explanation,
        )

        outcome.update(store=True, applied=[], failed=[])
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
