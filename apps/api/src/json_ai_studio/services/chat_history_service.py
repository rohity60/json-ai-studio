"""Chat history: turn storage, diff status lifecycle, LLM replay.

The session's ``conversation_history`` is server-authoritative. Each chat
turn stores a user turn and an assistant turn; assistant diffs carry a
``status`` (pending -> accepted | rejected, or failed) that accept/reject
endpoints update in place. On the next chat call the recent turns are
replayed to the LLM in the model's own output format, with statuses, so
follow-ups ("do it for all such elements", "try again but smaller")
resolve against what actually happened to earlier proposals.

Budgeting uses LiteLLM's token helpers (no memory framework): whole
user/assistant pairs are dropped oldest-first until the history fits.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable
from uuid import uuid4

import litellm

from ..db.session_store import store
from ..settings import get_settings
from .errors import ConflictError
from .session_service import get_session, now_iso

logger = logging.getLogger("json_ai_studio.chat_history")

TERMINAL_STATUSES = frozenset({"accepted", "rejected", "failed"})


# -- Storage ---------------------------------------------------------------


def _history(session: dict[str, Any]) -> list[dict[str, Any]]:
    return session.setdefault("conversation_history", [])


def make_turn(
    role: str,
    content: str,
    *,
    diffs: list[dict[str, Any]] | None = None,
    kind: str = "message",
) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "role": role,
        "kind": kind,
        "content": content,
        "diffs": diffs,
        "created_at": now_iso(),
    }


def append_turns(session: dict[str, Any], *turns: dict[str, Any]) -> None:
    """Append turns and prune the oldest beyond the stored-turn cap."""
    history = _history(session)
    history.extend(turns)
    cap = get_settings().chat_history_max_stored_turns
    if len(history) > cap:
        del history[: len(history) - cap]


def append_boundary(session: dict[str, Any], content: str) -> dict[str, Any]:
    turn = make_turn("assistant", content, kind="boundary")
    append_turns(session, turn)
    return turn


def iter_diffs(session: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for turn in _history(session):
        for diff in turn.get("diffs") or []:
            yield diff


def find_diff(session: dict[str, Any], diff_id: str) -> dict[str, Any] | None:
    for turn in reversed(_history(session)):
        for diff in turn.get("diffs") or []:
            if diff.get("id") == diff_id:
                return diff
    return None


def pending_diffs(session: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for d in iter_diffs(session) if d.get("status", "pending") == "pending"]


def mark_all_pending(session: dict[str, Any], status: str) -> int:
    """Move every pending diff to ``status``; return how many changed."""
    changed = pending_diffs(session)
    for diff in changed:
        diff["status"] = status
    return len(changed)


def diff_ids_with_status(session: dict[str, Any], status: str) -> list[str]:
    return [d.get("id", "") for d in iter_diffs(session) if d.get("status") == status]


async def clear_chat(session_id: str) -> None:
    """Drop the chat thread. Refused while diffs are pending: their ids
    would vanish and they could no longer be accepted/rejected singly."""
    session = await get_session(session_id)
    pending = pending_diffs(session)
    if pending:
        raise ConflictError(
            f"{len(pending)} pending change(s); accept or reject them first"
        )
    session["conversation_history"] = []
    session["updated_at"] = now_iso()
    await store.save_session(session)
    logger.info("chat cleared session=%s", session_id)


# -- LLM replay ------------------------------------------------------------


def _compact_value(value: Any, max_chars: int) -> Any:
    """Return value as-is when small, else a truncated JSON string."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return value
    return text[:max_chars] + "…(truncated)"


def _assistant_payload(turn: dict[str, Any]) -> str:
    """Serialise an assistant turn in the model's own output contract.

    old_value is kept (compacted): it carries the change's *condition*
    ("99 -> 60"), which "do it for all" follow-ups generalise from. The
    prompt's H1 rule still forces fresh values from the CURRENT WORKING JSON.
    """
    settings = get_settings()
    diffs = turn.get("diffs") or []
    cap = settings.chat_history_max_diffs_per_turn
    out: list[dict[str, Any]] = []
    for diff in diffs[:cap]:
        entry: dict[str, Any] = {
            "path": diff.get("path", ""),
            "operation": diff.get("operation", ""),
            "old_value": _compact_value(
                diff.get("old_value"), settings.chat_history_value_max_chars
            ),
            "new_value": _compact_value(
                diff.get("new_value"), settings.chat_history_value_max_chars
            ),
            "status": diff.get("status", "pending"),
        }
        if diff.get("status") == "failed" and diff.get("failure_reason"):
            entry["failure_reason"] = diff["failure_reason"]
        out.append(entry)
    if len(diffs) > cap:
        rest = diffs[cap:]
        counts: dict[str, int] = {}
        for diff in rest:
            status = diff.get("status", "pending")
            counts[status] = counts.get(status, 0) + 1
        summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
        out.append({"note": f"…and {len(rest)} more diffs ({summary})"})
    payload: dict[str, Any] = {"diffs": out}
    if turn.get("bulk"):
        payload["bulk"] = turn["bulk"]
    if turn.get("question"):
        payload["question"] = turn["question"]
    payload["explanation"] = turn.get("content", "")
    return json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )


def _replayable_pairs(session: dict[str, Any]) -> list[list[dict[str, str]]]:
    """User/assistant message pairs after the last boundary, oldest first."""
    history = _history(session)
    start = 0
    for i, turn in enumerate(history):
        if turn.get("kind") == "boundary":
            start = i + 1
    pairs: list[list[dict[str, str]]] = []
    pending_user: dict[str, Any] | None = None
    for turn in history[start:]:
        if turn.get("kind") == "boundary":
            continue
        if turn.get("role") == "user":
            pending_user = turn
        elif turn.get("role") == "assistant" and pending_user is not None:
            pairs.append(
                [
                    {"role": "user", "content": pending_user.get("content", "")},
                    {"role": "assistant", "content": _assistant_payload(turn)},
                ]
            )
            pending_user = None
    return pairs


def _count_tokens(model: str, messages: list[dict[str, str]]) -> int:
    if not messages:
        return 0
    try:
        return litellm.token_counter(model=model, messages=messages)
    except Exception:  # unknown tokenizer → rough 4 chars/token estimate
        return sum(len(m.get("content", "")) for m in messages) // 4


def build_history_messages(
    session: dict[str, Any], model: str = ""
) -> list[dict[str, str]]:
    """Recent turns as LLM messages, bounded by pair count and tokens."""
    settings = get_settings()
    if not settings.chat_history_enabled:
        return []
    pairs = _replayable_pairs(session)
    total = len(pairs)
    pairs = pairs[-settings.chat_history_max_turns :] if pairs else []
    flat = [m for pair in pairs for m in pair]
    while pairs and _count_tokens(model, flat) > settings.chat_history_max_tokens:
        pairs = pairs[1:]
        flat = [m for pair in pairs for m in pair]
    logger.info(
        "history session=%s pairs_sent=%d pairs_dropped=%d",
        session.get("id"),
        len(pairs),
        total - len(pairs),
    )
    return flat


def fit_to_context(
    model: str,
    system_prompt: str,
    history: list[dict[str, str]],
    message: str,
    reserve_output: int,
) -> list[dict[str, str]]:
    """Assemble [system, *history, user], dropping history to fit the window.

    History is always sacrificed before the system prompt (which carries the
    authoritative CURRENT WORKING JSON).
    """
    system = {"role": "system", "content": system_prompt}
    user = {"role": "user", "content": message}
    max_input: int | None = None
    try:
        info = litellm.get_model_info(model)
        max_input = info.get("max_input_tokens") or info.get("max_tokens")
    except Exception:
        max_input = None
    if max_input and history:
        budget = max_input - reserve_output
        while history and _count_tokens(model, [system, *history, user]) > budget:
            history = history[2:]  # drop oldest pair
    return [system, *history, user]
