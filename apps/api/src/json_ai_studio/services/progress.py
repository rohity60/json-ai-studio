"""User-facing turn progress (PRD B §8, B-50..B-56).

Every message is built here, in code, from the plan, the tool name/args/
result and the deployment budget — never by the model: zero extra LLM
tokens on a 16k/min budget, always accurate, available immediately even
when the provider does not stream (Google tool rounds).

Messages carry only JSON paths, sizes, counts and the user's own search
terms (shortened) — never document values (B-56).
"""

from __future__ import annotations

import json
import math
from typing import Any

from ..providers.policy import policy_of, transient_wait
from . import deployment_budget as budget

_TERM_MAX = 40  # chars of a user search term shown back
_AVG_CALL_S = 4.0  # typical model call latency used for the ETA
_GROWTH_THRESHOLD = 3  # first call > 1/3 of the budget → later steps 1/window


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"


def _term(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= _TERM_MAX else text[: _TERM_MAX - 1] + "…"


def _duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds} s"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} min"


# ---------------------------------------------------------------------------
# Plan (B-50)
# ---------------------------------------------------------------------------


def calls_per_min(deployment: Any, model: str, est_tokens: int) -> float | None:
    """How many calls of ~est_tokens this deployment allows per minute
    (pacing and token budget), or None when it has no limits."""
    limits: list[float] = []
    interval = float(getattr(deployment, "min_call_interval_s", 0) or 0)
    if interval > 0:
        limits.append(60.0 / interval)
    usable = budget.plan_budget(deployment)
    if usable and est_tokens > 0:
        # Our estimate × the provider's observed ratio for this model.
        tokens = budget.calibrated(budget.budget_key(deployment, model), est_tokens)
        limits.append(usable / max(tokens, 1))
    return min(limits) if limits else None


def _rounds_outgrow_window(deployment: Any, model: str, est_tokens: int) -> bool:
    """True when the first call already uses over a third of the usable
    per-minute budget. Live (Google, 2026-11-12): rounds grew 5.7k → 8.5k
    tokens against 12.8k usable, so from step 2 only one fit per minute."""
    usable = budget.plan_budget(deployment)
    if not usable or est_tokens <= 0:
        return False
    tokens = budget.calibrated(budget.budget_key(deployment, model), est_tokens)
    return tokens * _GROWTH_THRESHOLD > usable


def retry_allowance_s(deployment: Any) -> float:
    """Extra time one call may take when the provider errors and the
    deployment policy retries it: every scheduled cooldown plus the repeat
    calls (B-28a, static; learned rates come with B-28)."""
    pol = policy_of(deployment)
    attempts = max(0, int(pol.transient_retry_attempts))
    return sum(transient_wait(pol, n) + _AVG_CALL_S for n in range(1, attempts + 1))


def plan_event(
    mode: str, steps: int, deployment: Any, model: str, est_tokens: int
) -> str:
    """`plan` SSE event sent once, before the first model call."""
    cpm = calls_per_min(deployment, model, est_tokens)
    if cpm is not None and cpm > 0:
        per_step = max(60.0 / cpm, _AVG_CALL_S)
        if steps > 1 and _rounds_outgrow_window(deployment, model, est_tokens):
            # Every lookup step resends the earlier results, so later steps
            # grow past half the per-minute budget: one step per window.
            per_step = max(per_step, budget.window_span(deployment))
            cpm = min(cpm, 60.0 / per_step)
        eta_s = (steps - 1) * per_step + _AVG_CALL_S
    else:
        eta_s = steps * _AVG_CALL_S
    retry_s = retry_allowance_s(deployment)
    if mode == "inline" or steps <= 1:
        message = "Sending your request to the AI model…"
    else:
        message = f"Large document — the AI will look things up in up to {steps} steps"
        if cpm is not None and cpm < 4:
            per_min = max(1, int(cpm)) if cpm >= 1 else 1
            message += (
                f". This AI model allows about {per_min} step"
                f"{'s' if per_min != 1 else ''} per minute, so this may take "
                f"up to ~{_duration(eta_s)}"
            )
            if retry_s:
                message += (
                    f" (up to ~{_duration(eta_s + retry_s)} if the AI provider "
                    "has temporary errors — it retries automatically)"
                )
            message += "."
        else:
            message += "."
    return sse(
        "plan",
        {
            "mode": mode,
            "rounds_planned": max(0, steps - 1),
            "steps": steps,
            "calls_per_min": round(cpm, 2) if cpm is not None else None,
            "eta_s": int(round(eta_s)),
            "eta_max_s": int(round(eta_s + retry_s)),
            "message": message,
        },
    )


# ---------------------------------------------------------------------------
# Stage progress (B-51, B-52)
# ---------------------------------------------------------------------------


def progress_event(
    stage: str, message: str, step: int | None = None, steps: int | None = None
) -> str:
    data: dict[str, Any] = {"stage": stage, "message": message}
    if step is not None:
        data["step"] = step
    if steps is not None:
        data["steps"] = steps
    return sse("progress", data)


def calling(step: int, steps: int, final: bool) -> str:
    if steps <= 1:
        return progress_event("calling", "Asking the AI model…", 1, 1)
    if final:
        return progress_event(
            "answering", f"Step {step}/{steps} — writing the answer", step, steps
        )
    return progress_event(
        "calling", f"Step {step}/{steps} — asking the AI model", step, steps
    )


def applying(count: int) -> str:
    noun = "change" if count == 1 else "changes"
    return progress_event("applying", f"Applying {count} {noun}…")


# ---------------------------------------------------------------------------
# Tool calls (B-53)
# ---------------------------------------------------------------------------


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def describe_tool_call(
    name: str, raw_args: Any, result: dict[str, Any] | None, doc: Any = None
) -> str:
    """One past-tense line for a finished tool call, from its real result."""
    try:
        args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
    except (TypeError, ValueError):
        args = {}
    if not isinstance(args, dict):
        args = {}
    result = result if isinstance(result, dict) else {}
    if "error" in result:
        return f"Lookup ({name}) could not run: {_term(result['error'])}"

    if name == "search":
        term = _term(args.get("query"))
        scope = str(args.get("scope", "values")).lower()
        where = {"keys": "field names", "both": "field names and values"}.get(
            scope, "values"
        )
        total = int(result.get("total") or 0)
        found = "no matches" if total == 0 else _count(total, "match", "matches")
        prefix = args.get("path_prefix")
        inside = f" in {prefix}" if prefix else ""
        return f"Searched {where}{inside} for “{term}” — {found}"

    if name == "query":
        path = str(args.get("path") or "")
        total = int(result.get("total") or 0)
        cond = " with conditions" if args.get("where") else ""
        found = (
            "nothing matched"
            if total == 0
            else f"{_count(total, 'item', 'items')} matched"
        )
        return f"Queried {path}{cond} — {found}"

    if name == "read":
        path = str(args.get("path") or "") or "the document"
        size = _value_size(doc, path)
        if "text" in result and "length" in result:  # one page of a long string
            start = int(result.get("offset") or 0)
            end = start + len(str(result.get("text") or ""))
            return (
                f"Read {path} (characters {start + 1:,}–{end:,} "
                f"of {int(result['length']):,})"
            )
        if "value_truncated" in result:
            shown = len(str(result.get("value_truncated") or ""))
            total = f" of {size:,}" if size else ""
            return f"Read {path} (first {shown:,}{total} characters)"
        return f"Read {path}" + (
            f" ({_count(size, 'character', 'characters')})" if size else ""
        )

    return f"Looked up {name}"


def _value_size(doc: Any, path: str) -> int:
    """Serialised size of the value at a JSON Pointer (0 if unknown)."""
    if doc is None:
        return 0
    node = doc
    for part in [p for p in path.split("/")[1:] if p]:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return 0
    if isinstance(node, str):
        return len(node)
    return len(json.dumps(node, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# Waits and retries (B-54, B-55)
# ---------------------------------------------------------------------------

WAIT_MESSAGES = {
    "pacing": "Spacing requests to stay within this AI model's limit",
    "tokens": "This AI model's per-minute limit is used up — continuing shortly",
    "cooldown": "The AI provider had a temporary error — cooling down before retrying",
}


def waiting_event(seconds: float, reason: str, step: int | None = None) -> str:
    data: dict[str, Any] = {
        "retry_after": max(1, math.ceil(seconds)),
        "reason": reason,
        "message": WAIT_MESSAGES.get(reason, "Waiting for AI model capacity…"),
    }
    if step is not None:
        data["step"] = step
    return sse("waiting", data)


def retrying_event(attempt: int, max_attempts: int, wait_s: float, kind: str) -> str:
    if kind == "rate_limit":
        message = f"The AI model is busy — retrying ({attempt}/{max_attempts})"
    else:
        message = (
            "The AI provider had a temporary error — retrying "
            f"({attempt}/{max_attempts})"
        )
    return sse(
        "retrying",
        {
            "attempt": attempt,
            "max": max_attempts,
            "wait_s": round(wait_s, 1),
            "kind": kind,
            "message": message,
        },
    )
