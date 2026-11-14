"""Failed-turn traces and resume (PRD B §5, ADR-0028).

A chat turn that fails mid-way (provider error, call timeout, model
capacity, client disconnect) is stored with ``status`` failed/interrupted.
Its ``trace`` — what the tool loop had done when it stopped — lives in
server memory only, in ``session["turn_traces"][turn_id]``, never on a turn
dict (so it never reaches the wire) and never sent to the model verbatim:

    {json_hash, focus_path, plan, calls, error_code,
     round_reached, messages_snapshot, tool_calls: [{id, round, name, args,
     result_chars, paths, hashes}]}

``messages_snapshot`` is the conversation after the last finished lookup
round, without the system prompt (rebuilt fresh on resume). ``hashes`` maps
each path a lookup depended on to a hash of its value, so a resume after the
document changed can drop exactly the lookups that went stale (B-44).
Only the latest turn keeps a trace; it is dropped when a later turn
completes (B-47). Lost on a backend restart — accepted.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..diff_utils import DiffApplyError, _split_path

FAILED_STATUSES = frozenset({"failed", "interrupted"})
TRACES_KEY = "turn_traces"
READ_PATHS_MAX = 20
_ARGS_MAX = 200
_RANGE = re.compile(r"^(.*)/(\d+)\.\.(\d*)$")
_MISSING = "missing"


# -- Hashing ---------------------------------------------------------------


def _digest(value: Any) -> str:
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_hash(doc: Any) -> str:
    """sha256 of the compact document (B-41 ``json_hash``)."""
    return _digest(doc)


def _value(doc: Any, path: str) -> Any:
    try:
        parts = _split_path(path or "")
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


def value_hash(doc: Any, path: str) -> str:
    value = _value(doc, path)
    return _MISSING if value is _MISSING else _digest(value)[:16]


# -- Recording -------------------------------------------------------------


def new_trace(doc: Any, focus_path: str | None = None) -> dict[str, Any]:
    return {
        "json_hash": json_hash(doc),
        "focus_path": focus_path or None,
        "plan": None,
        "calls": 0,
        "error_code": None,
        "round_reached": 0,
        "messages_snapshot": None,
        "tool_calls": [],
    }


def count_call(trace: dict[str, Any] | None) -> None:
    """One model call is about to go out."""
    if trace is not None:
        trace["calls"] = trace.get("calls", 0) + 1


def _args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _scope(path: str) -> str:
    """Static part of a scope path: drop an index range or wildcard tail."""
    m = _RANGE.match(path)
    if m:
        return m.group(1)
    parts = path.split("/")
    for i, part in enumerate(parts):
        if part == "*":
            return "/".join(parts[:i])
    return path


def paths_of_call(name: str, raw_args: Any, result: Any) -> list[str]:
    """JSON paths a lookup's result depends on (relative to the toolbox doc).

    read → the paths actually returned (batch) or the one path;
    search/query/outline → the subtree they looked in ("" = whole doc).
    """
    args = _args(raw_args)
    if name == "read":
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            return [
                str(r["path"])
                for r in result["results"]
                if isinstance(r, dict) and "path" in r
            ]
        return [str(args.get("path", "") or "")]
    if name == "search":
        return [_scope(str(args.get("path_prefix", "") or ""))]
    if name in ("query", "outline"):
        return [_scope(str(args.get("path", "") or ""))]
    return [""]


def record_round(
    trace: dict[str, Any] | None,
    round_no: int,
    messages: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    doc: Any,
) -> None:
    """A lookup round finished: snapshot the conversation (no system
    prompt) and the calls with the hashes of what they read."""
    if trace is None:
        return
    trace["round_reached"] = round_no + 1
    trace["messages_snapshot"] = list(messages[1:])
    for call in calls:
        paths = paths_of_call(call["name"], call["args"], call.get("result"))
        trace["tool_calls"].append(
            {
                "id": call["id"],
                "round": round_no + 1,
                "name": call["name"],
                "args": str(call["args"])[:_ARGS_MAX],
                "result_chars": call["result_chars"],
                "paths": paths,
                "hashes": {p: value_hash(doc, p) for p in paths},
            }
        )


# -- Resume ----------------------------------------------------------------


def _stale_note(paths: list[str]) -> str:
    shown = ", ".join(p or "/" for p in paths[:5])
    return json.dumps(
        {
            "error": f"stale: {shown} changed since this lookup; look it up "
            "again if you still need it"
        }
    )


def resume_messages(
    trace: dict[str, Any], doc: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Snapshot to continue from, and the lookups still valid.

    Unchanged document → the snapshot as-is. Changed document (B-44) →
    each lookup whose paths now hash differently has its result replaced by
    a short "stale, read again" note (the tool-call/result pairing the API
    requires stays intact); the rest is kept. None when nothing is
    reusable: the caller re-sends the original message instead.
    """
    snapshot = trace.get("messages_snapshot")
    if not snapshot:
        return None
    calls = list(trace.get("tool_calls") or [])
    if not trace.get("doc_changed"):
        return list(snapshot), calls
    stale: dict[str, list[str]] = {}
    for call in calls:
        changed = [
            p for p, h in (call.get("hashes") or {}).items() if value_hash(doc, p) != h
        ]
        if changed:
            stale[call["id"]] = changed
    kept = [c for c in calls if c["id"] not in stale]
    if not kept:
        return None
    messages = [
        (
            {**m, "content": _stale_note(stale[m.get("tool_call_id")])}
            if m.get("role") == "tool" and m.get("tool_call_id") in stale
            else m
        )
        for m in snapshot
    ]
    return messages, kept


# -- Turn records ----------------------------------------------------------


def read_paths(trace: dict[str, Any] | None, prefix: str | None = None) -> list[str]:
    """Paths the failed attempt read (deduplicated, at most READ_PATHS_MAX),
    re-anchored on the full document when the turn had a focus_path."""
    if not trace:
        return []
    seen: list[str] = []
    for call in trace.get("tool_calls") or []:
        if call.get("name") != "read":
            continue
        for p in call.get("paths") or []:
            full = (prefix or "") + p
            if full and full not in seen:
                seen.append(full)
    return seen[:READ_PATHS_MAX]


_REASONS = {
    "provider_error": "the AI provider returned an error",
    "timeout": "the AI model took too long to answer",
    "rate_limit": "the AI model reached its per-minute capacity",
    "internal_error": "something went wrong on our side",
    "interrupted": "the connection was closed",
}


def failure_content(code: str, rounds: int) -> str:
    """User-facing text of a failed/interrupted assistant turn."""
    reason = _REASONS.get(code, "the request failed")
    done = f" after {rounds} lookup step{'s' if rounds != 1 else ''}" if rounds else ""
    return (
        f"This attempt stopped{done}: {reason}. No changes were made. "
        "Continue picks up where it stopped."
    )


def replay_summary(turn: dict[str, Any]) -> str:
    """Compact note replayed to the model for a failed turn (B-45) —
    never the tool results themselves."""
    word = "interrupted" if turn.get("status") == "interrupted" else "failed"
    code = turn.get("error_code") or word
    paths = turn.get("read_paths") or []
    read = (
        "read: " + ", ".join(paths) if paths else "nothing was read from the document"
    )
    return f"(previous attempt {word}: {code}; {read})"


def traces(session: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return session.setdefault(TRACES_KEY, {})


def keep_only(session: dict[str, Any], turn_id: str, trace: dict[str, Any]) -> None:
    """Store ``trace`` as the session's only one (only the latest turn can
    be resumed)."""
    session[TRACES_KEY] = {turn_id: trace}


def drop_all(session: dict[str, Any]) -> None:
    """A later turn completed: earlier failures are no longer resumable."""
    session[TRACES_KEY] = {}
