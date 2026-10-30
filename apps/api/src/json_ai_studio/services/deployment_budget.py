"""Deployment-level input-token budget (ADR-0025).

Providers cap input tokens per minute per model (Google free tier: 16k for
gemma-4-26b), shared by every caller behind one key. This module tracks
what we sent to each deployment+model in a sliding 60 s window so the
gateway can wait or reject *before* the provider would 429.

Independent of credit_service (per-user caps, ADR-0015): separate keys and
storage; a deployment wait or rejection never touches a user's quota.

Every LLM call (each tool round counts) waits for its pacing slot
(claim_slot, min_call_interval_s apart per deployment), then does
try_reserve(estimate) → call →
settle(actual prompt tokens) or release() on failure. settle() also feeds a
per-key calibration ratio (provider tokens ÷ our estimate), because LiteLLM
does not know every tokenizer (Gemma). The functions never await between
check and append, so they are atomic on the event loop. In-memory and
per-process: with N workers each would allow the full limit.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import litellm

from ..settings import get_settings

logger = logging.getLogger("json_ai_studio.deployment_budget")

WINDOW_S = 60.0
_RATIO_ALPHA = 0.3  # weight of the newest observation in the moving average
_RATIO_BOUNDS = (0.5, 3.0)

# key -> deque of [timestamp, tokens]; entries are mutable so settle() can
# replace an estimate with the provider's count in place.
_windows: dict[str, deque[list[float]]] = {}
_blocked_until: dict[str, float] = {}
_next_slot: dict[str, float] = {}  # key -> earliest start of the next call
_ratio: dict[str, float] = {}


@dataclass
class Reservation:
    key: str
    entry: list[float] | None  # None = deployment has no budget
    raw_estimate: int


def budget_key(deployment: Any, model: str) -> str:
    return f"{getattr(deployment, 'name', '?')}:{model}"


def tpm_limit(deployment: Any) -> int | None:
    return getattr(deployment, "tpm_input_limit", None) or None


def plan_budget(deployment: Any) -> int | None:
    """Tokens one turn may plan for: the per-minute limit minus headroom."""
    limit = tpm_limit(deployment)
    if limit is None:
        return None
    return int(limit * get_settings().deployment_budget_headroom)


def estimate_tokens(model: str, messages: list[dict[str, Any]]) -> int:
    """Raw (uncalibrated) prompt token estimate for `messages`."""
    if not messages:
        return 0
    try:
        return int(litellm.token_counter(model=model, messages=messages))
    except Exception:  # unknown tokenizer → rough 4 chars/token
        return sum(len(str(m.get("content") or "")) for m in messages) // 4


def calibrated(key: str, raw_estimate: int) -> int:
    return math.ceil(raw_estimate * _ratio.get(key, 1.0))


def _prune(key: str, now: float) -> deque[list[float]]:
    q = _windows.setdefault(key, deque())
    while q and q[0][0] <= now - WINDOW_S:
        q.popleft()
    return q


def claim_slot(deployment: Any, model: str) -> float:
    """Claim the next call slot on this deployment; seconds until it starts.

    Calls are spaced min_call_interval_s apart across all turns and users,
    so a burst (several users, or a multi-round tool turn) is spread over
    the minute instead of hitting the provider's per-minute cap at once.
    """
    interval = getattr(deployment, "min_call_interval_s", 0) or 0
    if interval <= 0:
        return 0.0
    key = budget_key(deployment, model)
    now = time.monotonic()
    start = max(now, _next_slot.get(key, 0.0))
    _next_slot[key] = start + interval
    return start - now


def try_reserve(
    deployment: Any, model: str, raw_estimate: int
) -> tuple[Reservation | None, float]:
    """Claim calibrated(raw_estimate) tokens now, or say how long to wait.

    Returns (reservation, 0) on success, else (None, seconds until enough of
    the window frees up; inf when the call can never fit the limit).
    """
    key = budget_key(deployment, model)
    # Gate at limit × headroom, not the full limit: Google's free tier starts
    # answering 500 (then 429) at ~14.5k of its 16k/min (log 2026-10-30).
    limit = plan_budget(deployment)
    if limit is None:
        return Reservation(key, None, raw_estimate), 0.0
    tokens = calibrated(key, raw_estimate)
    now = time.monotonic()
    blocked = _blocked_until.get(key, 0.0)
    if now < blocked:
        return None, blocked - now
    if tokens > limit:
        return None, math.inf
    q = _prune(key, now)
    used = sum(t for _, t in q)
    if used + tokens <= limit:
        entry = [now, float(tokens)]
        q.append(entry)
        logger.debug(
            "budget reserve key=%s tokens=%d used=%d limit=%d",
            key,
            tokens,
            used + tokens,
            limit,
        )
        return Reservation(key, entry, raw_estimate), 0.0
    need = used + tokens - limit
    freed = 0.0
    for ts, t in q:
        freed += t
        if freed >= need:
            return None, max(0.0, ts + WINDOW_S - now)
    return None, WINDOW_S  # unreachable while tokens <= limit


def settle(res: Reservation, actual_prompt_tokens: int) -> None:
    """Replace the estimate with the provider's count; update calibration."""
    if res.entry is None or actual_prompt_tokens <= 0:
        return
    res.entry[1] = float(actual_prompt_tokens)
    if res.raw_estimate > 0:
        observed = actual_prompt_tokens / res.raw_estimate
        old = _ratio.get(res.key, 1.0)
        new = (1 - _RATIO_ALPHA) * old + _RATIO_ALPHA * observed
        _ratio[res.key] = min(max(new, _RATIO_BOUNDS[0]), _RATIO_BOUNDS[1])
        logger.info(
            "budget settle key=%s estimated=%d actual=%d ratio=%.3f",
            res.key,
            res.raw_estimate,
            actual_prompt_tokens,
            _ratio[res.key],
        )


def release(res: Reservation) -> None:
    """Give back a reservation whose call failed before using tokens."""
    if res.entry is None:
        return
    q = _windows.get(res.key)
    if q is not None:
        try:
            q.remove(res.entry)
        except ValueError:
            pass


def block(deployment: Any, model: str, seconds: float) -> None:
    """Provider said 429: treat the window as full for `seconds`."""
    key = budget_key(deployment, model)
    _blocked_until[key] = max(
        _blocked_until.get(key, 0.0), time.monotonic() + max(0.0, seconds)
    )
    logger.info("budget blocked key=%s for %.1fs (provider 429)", key, seconds)


def reset() -> None:
    """Clear all state (tests)."""
    _windows.clear()
    _blocked_until.clear()
    _ratio.clear()
    _next_slot.clear()
