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
from ..text_edits import expand_text_edits
from ..diff_utils import (
    TRUNCATION_REASON,
    DiffApplyError,
    DiffUtils,
    _current_value,
    _split_path,
    parse_llm_response,
)
from ..settings import get_settings
from ..gateway import SERVICE_BUSY_MESSAGE, GatewayService
from . import chat_history_service, intent as intent_rules, progress
from . import review_proposal
from .turn_planner import plan_turn
from .session_service import now_iso

logger = logging.getLogger("json_ai_studio.chat")


def _truncation_note(diff: dict[str, Any], working_json: Any) -> str:
    """User-facing note for a diff the edit-safety guard refused."""
    path = str(diff.get("path") or "")
    try:
        _, old = _current_value(working_json, _split_path(path))
    except DiffApplyError:
        old = None
    new = diff.get("new_value")
    sizes = ""
    if isinstance(old, str) and isinstance(new, str):
        sizes = f" (from {len(old):,} to {len(new):,} characters)"
    return (
        f"NOT changed: {path}. The AI only saw part of this long field, and "
        f"its version would have cut the text{sizes}, so the field was left "
        "as it was. Any fixes described above for it were not made — ask "
        "again for just this field."
    )


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
    focus_path: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream LLM response as SSE events via GatewayService.

    The turn planner (ADR-0025) sizes the prompt to the chosen deployment.
    `focus_path` (JSON Pointer) limits what the model sees to one subtree;
    its diff and bulk paths are prefixed back onto the full document.

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
        model_json: Any = working_json
        if focus_path:
            model_json = _value_at(working_json, focus_path)
            if not isinstance(model_json, (dict, list)):
                yield sse(
                    "complete",
                    {
                        "working_json": working_json,
                        "explanation": (
                            f"The section {focus_path} was not found in the "
                            "current JSON. No changes were made."
                        ),
                    },
                )
                return
            logger.info("chat focus session=%s path=%s", session_id, focus_path)
        logger.debug("chat history session=%s messages=%s", session_id, history)

        def planner(deployment: Any, litellm_model: str):
            plan = plan_turn(
                model_json, message, list(history or []), deployment, litellm_model
            )
            messages = getattr(plan, "messages", None)
            if messages:
                logger.debug(
                    "chat system_prompt session=%s prompt=%s",
                    session_id,
                    messages[0]["content"],
                )
            return plan

        content_parts: list[str] = []
        error_payload: dict[str, Any] | None = None
        quota_hit = False
        async for event_text in GatewayService.invoke(
            session_id,
            message,
            principal,
            "",
            reasoning=reasoning,
            planner=planner,
        ):
            yield event_text
            event, payload = parse_sse(event_text)
            if event == "thinking" and payload is not None:
                text = payload.get("text")
                if isinstance(text, str):
                    content_parts.append(text)
            elif event == "error" and payload is not None:
                error_payload = payload
            elif event in (
                "rate_limit",
                "credit_limit",
                "service_unavailable",
                "input_too_large",
            ):
                quota_hit = True

        # The rate_limit/credit_limit/service_unavailable/input_too_large
        # event was already
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
        if focus_path:
            # The model saw only the focused subtree; re-anchor its paths.
            for d in diffs:
                if isinstance(d.get("path"), str):
                    d["path"] = focus_path + d["path"]
            for op in bulk_ops:
                if isinstance(op.get("path"), str):
                    op["path"] = focus_path + op["path"]
        if question:
            outcome["question"] = question
        # Find/replace inside long strings → one full-value modify per field,
        # computed against the FULL value the model may only have seen cut.
        diffs, text_notes = expand_text_edits(diffs, working_json)
        if text_notes:
            logger.info("text edits notes=%s", text_notes)
        bulk_notes: list[str] = list(text_notes)
        if bulk_ops:
            bulk_diffs, op_notes = expand_all(
                bulk_ops, working_json, get_settings().bulk_max_matches
            )
            bulk_notes.extend(op_notes)
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

        yield progress.applying(len(diffs))  # B-52
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
        guarded = [d for d, reason in failed if reason == TRUNCATION_REASON]
        other = [(d, reason) for d, reason in failed if reason != TRUNCATION_REASON]
        for d in guarded:
            # Edit-safety guard: say plainly that the field is unchanged —
            # the model's explanation above may describe fixes to it.
            notes.append(_truncation_note(d, working_json))
        if other:
            failed_desc = "; ".join(
                f"{d.get('path')} ({reason})" for d, reason in other
            )
            notes.append(
                f"Skipped {len(other)} proposed change(s) that did not match "
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

    except Exception:
        # Fail-fast error (ADR-0007): yield error in stream, don't retry.
        # Provider/deployment failures are already turned into a friendly
        # service_unavailable event inside GatewayService.invoke/explain;
        # this is the catch-all for anything else (diff application, JSON
        # parsing, session store, ...). Never surface the raw exception —
        # same friendly message as the provider-failure popup, full
        # traceback stays in the logs.
        logger.exception("chat stream failed")
        if outcome is not None:
            outcome["store"] = False
        yield sse(
            "complete",
            {"working_json": working_json, "explanation": SERVICE_BUSY_MESSAGE},
        )


def _job_proposal(
    session: dict[str, Any],
    working_json: dict[str, Any],
    message: str,
    history: list[dict[str, str]],
) -> dict[str, Any] | None:
    """JobProposal payload when this message is a whole-document review
    that does not fit one turn (ADR-0026); None → run the turn as usual.
    Never raises: a failed estimate must not break the chat."""
    if not get_settings().intent_review_enabled:
        return None
    if not intent_rules.might_be_review(message):
        return None
    try:
        intent = intent_rules.classify_intent(
            message, intent_rules.doc_stats(working_json)
        )
        if intent.kind != intent_rules.REVIEW:
            return None
        target = review_proposal.default_deployment()
        if target is None:
            return None
        return review_proposal.propose(working_json, message, intent, history, *target)
    except Exception:
        logger.exception("job proposal failed session=%s", session.get("id"))
        return None


async def chat_event_stream(
    session: dict[str, Any],
    working_json: dict[str, Any],
    message: str,
    principal,
    thinking: bool = False,
    focus_path: str | None = None,
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
        doc_at_start = session.get("working_json")

        # Whole-document review that cannot fit one turn: say what it costs
        # as a batch job instead of starting a lookup loop. No model call.
        proposal = (
            None
            if focus_path
            else _job_proposal(session, working_json, message, history)
        )
        if proposal is not None:
            yield sse("thinking", {"text": "Sizing the review..."})
            yield sse("job_proposal", proposal)
            explanation = review_proposal.explanation(proposal)
            user_turn = chat_history_service.make_turn("user", message)
            assistant_turn = chat_history_service.make_turn(
                "assistant", explanation, kind="job_proposal"
            )
            assistant_turn["job_proposal"] = proposal
            chat_history_service.append_turns(session, user_turn, assistant_turn)
            session["updated_at"] = now_iso()
            await store.save_session(session)
            logger.info(
                "chat job proposal session=%s scope=%s records=%d batches=%d eta_s=%d",
                session.get("id"),
                proposal["scope_path"] or "/",
                proposal["record_count"],
                proposal["batch_count"],
                proposal["eta_s"],
            )
            yield sse(
                "complete",
                {
                    "working_json": working_json,
                    "explanation": explanation,
                    "job_proposal": proposal,
                    "user_turn_id": user_turn["id"],
                    "assistant_turn_id": assistant_turn["id"],
                },
            )
            return

        outcome: dict[str, Any] = {}
        async for event_text in _stream_llm(
            session.get("id", "chat-session"),
            working_json,
            message,
            principal,
            reasoning=reasoning,
            history=history,
            outcome=outcome,
            focus_path=focus_path or None,
        ):
            event, payload = parse_sse(event_text)
            if event != "complete" or payload is None:
                yield event_text
                continue

            # Persist before the client sees "complete" so an immediate
            # accept/reject finds the diff ids in history.
            merged_json = payload.get("working_json")
            if (
                merged_json is not None
                and session.get("working_json") is not doc_at_start
            ):
                # A review batch (ADR-0026) changed the document while this
                # turn ran: put this turn's changes on top of the current
                # document instead of overwriting it with a stale copy.
                merged_json, _, stale = DiffUtils.apply_all_verbose(
                    [
                        {
                            k: d[k]
                            for k in ("path", "operation", "old_value", "new_value")
                        }
                        for d in outcome.get("applied", [])
                    ],
                    session["working_json"],
                )
                stale_paths = {d["path"] for d, _ in stale}
                for d in outcome.get("applied", []):
                    if d["path"] in stale_paths:
                        d.update(
                            status="failed",
                            failure_reason="the document changed while the AI worked",
                        )
                payload["working_json"] = merged_json
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

    except Exception:
        # Catch-all for failures in persistence (session store, chat
        # history) wrapping the inner stream — provider failures are
        # already handled as friendly events inside it. Never surface the
        # raw exception; full traceback stays in the logs.
        logger.exception("chat endpoint stream failed")
        yield sse(
            "complete",
            {"working_json": working_json, "explanation": SERVICE_BUSY_MESSAGE},
        )
