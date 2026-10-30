"""Turn planner (ADR-0025): pick the cheapest prompt that fits the budget.

Runs after the deployment is chosen and before the first LLM call. The
budget is min(model context − reserved output, deployment per-minute input
limit × headroom); the first call must fit it. A tool turn resends the
growing conversation every round, so later rounds each reserve their actual
size in the gateway and wait for the per-minute window when it is full. Estimates come from the real messages
(system prompt, history, user message), calibrated per deployment.

Two views only, as before ADR-0025 — the budget just moves the line:
  inline   — full document, one call.
  skeleton — key-union skeleton + lookup tools on the full document
             (full CHAT_TOOL_MAX_ROUNDS; rounds may wait for capacity).
  TooLarge — nothing is sent; the caller emits `input_too_large` with the
             sections that would fit and a trimmed copy for the user (the
             trimmer is never used for what the model sees).
History is dropped before giving up on a rung. Without any known budget
the planner reproduces the pre-ADR-0025 behaviour.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import litellm

from ..json_tools import JsonToolbox
from ..json_trim import fit_trim
from ..prompting import build_system_prompt, is_skeleton_mode
from ..settings import get_settings
from . import chat_history_service
from . import deployment_budget as budget

logger = logging.getLogger("json_ai_studio.turn_planner")

_MAX_SECTIONS = 8
_SAMPLE_CHARS = 20_000


@dataclass
class TurnPlan:
    mode: str  # "inline" | "skeleton"
    messages: list[dict[str, Any]]
    toolbox: JsonToolbox | None
    max_rounds: int
    raw_estimate: int  # first call, uncalibrated


@dataclass
class TooLarge:
    doc_kb: int
    max_kb: int
    sections: list[dict[str, Any]]
    trimmed: dict[str, Any] | None  # {"working_json", "cuts"}


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def context_budget(deployment: Any, litellm_model: str) -> int | None:
    window = getattr(deployment, "context_tokens", None)
    if not window:
        try:
            info = litellm.get_model_info(litellm_model)
            window = info.get("max_input_tokens") or info.get("max_tokens")
        except Exception:
            window = None
    if not window:
        return None
    return max(0, int(window) - get_settings().llm_max_tokens)


def turn_budget(deployment: Any, litellm_model: str) -> int | None:
    limits = [
        b
        for b in (
            budget.plan_budget(deployment),
            context_budget(deployment, litellm_model),
        )
        if b is not None
    ]
    return min(limits) if limits else None


def plan_turn(
    working_json: Any,
    message: str,
    history: list[dict[str, str]],
    deployment: Any,
    litellm_model: str,
) -> TurnPlan | TooLarge:
    settings = get_settings()
    tools_ok = settings.chat_tools_enabled and bool(
        getattr(deployment, "supports_tools", False)
    )
    key = budget.budget_key(deployment, litellm_model)
    limit = turn_budget(deployment, litellm_model)

    def messages_for(prompt: str, hist: list[dict[str, str]]) -> list[dict[str, Any]]:
        return chat_history_service.fit_to_context(
            litellm_model,
            prompt,
            list(hist),
            message,
            reserve_output=settings.llm_max_tokens,
        )

    def estimate(msgs: list[dict[str, Any]]) -> tuple[int, int]:
        raw = budget.estimate_tokens(litellm_model, msgs)
        return raw, budget.calibrated(key, raw)

    if limit is None:
        # No known budget: pre-ADR-0025 behaviour (size-based mode).
        skeleton = is_skeleton_mode(working_json)
        prompt = build_system_prompt(working_json, has_history=bool(history))
        msgs = messages_for(prompt, history)
        return TurnPlan(
            mode="skeleton" if skeleton else "inline",
            messages=msgs,
            toolbox=(
                JsonToolbox(working_json, settings.chat_tool_result_max_chars)
                if skeleton
                else None
            ),
            max_rounds=settings.chat_tool_max_rounds,
            raw_estimate=0,
        )

    def toolbox() -> JsonToolbox | None:
        if not tools_ok:
            return None
        return JsonToolbox(working_json, settings.chat_tool_result_max_chars)

    histories = [history, []] if history else [[]]

    # 1. Inline: one call, no tools.
    if not is_skeleton_mode(working_json):
        for hist in histories:
            prompt = build_system_prompt(
                working_json, has_history=bool(hist), mode="inline"
            )
            msgs = messages_for(prompt, hist)
            raw, cost = estimate(msgs)
            if cost <= limit:
                return _log(TurnPlan("inline", msgs, None, 0, raw), limit, cost)

    # 2. Skeleton (+ tools). Only the first call must fit: later tool
    # rounds reserve their actual size and wait for the window if needed.
    rounds = settings.chat_tool_max_rounds if tools_ok else 0
    for hist in histories:
        prompt = build_system_prompt(
            working_json, has_history=bool(hist), mode="skeleton"
        )
        msgs = messages_for(prompt, hist)
        raw, cost = estimate(msgs)
        if cost <= limit:
            return _log(TurnPlan("skeleton", msgs, toolbox(), rounds, raw), limit, cost)

    return _too_large(working_json, message, limit, key, litellm_model, messages_for)


def _log(plan: TurnPlan, limit: int, cost: int) -> TurnPlan:
    logger.info(
        "turn plan mode=%s est_tokens=%d budget=%d max_rounds=%d tools=%s",
        plan.mode,
        cost,
        limit,
        plan.max_rounds,
        plan.toolbox is not None,
    )
    return plan


def _too_large(
    working_json: Any,
    message: str,
    limit: int,
    key: str,
    litellm_model: str,
    messages_for: Any,
) -> TooLarge:
    """Sizes in KB (never tokens), the sections that fit, a trimmed copy."""
    compact = _compact(working_json)
    sample = compact[:_SAMPLE_CHARS]
    sample_tokens = budget.calibrated(
        key,
        budget.estimate_tokens(litellm_model, [{"role": "user", "content": sample}]),
    )
    chars_per_token = len(sample) / max(1, sample_tokens)
    empty_prompt = build_system_prompt({}, mode="inline")
    overhead = budget.calibrated(
        key, budget.estimate_tokens(litellm_model, messages_for(empty_prompt, []))
    )
    max_chars = int(max(0, limit - overhead) * chars_per_token)

    sections: list[dict[str, Any]] = []
    frontier: list[tuple[str, Any, int]] = [("", working_json, 0)]
    while frontier:
        path, node, depth = frontier.pop(0)
        if not isinstance(node, dict):
            continue
        for k, v in node.items():
            child = f"{path}/{str(k).replace('~', '~0').replace('/', '~1')}"
            size = len(_compact(v))
            if size <= max_chars and isinstance(v, (dict, list)):
                sections.append({"path": child, "kb": max(1, round(size / 1024))})
            elif depth < 1:
                frontier.append((child, v, depth + 1))
    # Top-level sections first (they are what users recognise), then bigger
    # ones — size alone pushed /defaults out behind 8 tenant subtrees.
    sections.sort(key=lambda s: (s["path"].count("/"), -s["kb"]))

    def fits_copy(trimmed: Any, cuts: list[dict[str, Any]]) -> bool:
        return len(_compact(trimmed)) <= max_chars

    copy = fit_trim(working_json, fits_copy, min_items=1, allow_key_cap=True)
    result = TooLarge(
        doc_kb=max(1, round(len(compact) / 1024)),
        max_kb=max(1, round(max_chars / 1024)) if max_chars else 0,
        sections=sections[:_MAX_SECTIONS],
        trimmed=(
            {"working_json": copy[0], "cuts": copy[1]} if copy is not None else None
        ),
    )
    logger.info(
        "turn plan mode=too_large doc_kb=%d max_kb=%d budget=%d overhead=%d "
        "sections=%d trimmed=%s",
        result.doc_kb,
        result.max_kb,
        limit,
        overhead,
        len(result.sections),
        copy is not None,
    )
    return result
