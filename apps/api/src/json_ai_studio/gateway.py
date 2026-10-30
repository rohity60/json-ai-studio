"""AI Gateway — cost calculation, credit tracking, usage logging.

Centralized LiteLLM integration. All LLM calls flow through GatewayService.
Calculates cost from token counts, deducts credits via credit_service
(principal-aware, ADR-0015), logs usage.
Emits SSE events: deployment -> thinking -> usage -> complete.

Model selection (ADR-0016): explicit model > profile mapping > config
default — DeploymentRegistry.pick_default() round-robins enabled
deployments, each serving its own base_model from deployments.yaml.
Pricing lives on the provider classes; MODEL_PRICING is only a legacy
fallback for models no deployment serves.

Quota errors are never raised after the stream has started: pre-stream
429/402 become SSE `rate_limit` / `credit_limit` events carrying
`login_available` so the frontend can offer login as the fix.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable

import litellm
from fastapi import HTTPException

from .auth import Principal, mask_secret
from .deployment import DeploymentRegistry
from .providers import DeploymentProvider
from .json_tools import JsonToolbox
from .services import chat_history_service, credit_service
from .services import deployment_budget as budget
from .services.turn_planner import TooLarge, TurnPlan
from .settings import get_settings

logger = logging.getLogger("json_ai_studio.gateway")

# No "Give Feedback / Get Help" banner on stdout for every provider error;
# the error itself is logged below.
litellm.suppress_debug_info = True

# Shown to users when a deployment/provider call fails (any cause). Raw
# provider errors go to server logs only — never to the client.
SERVICE_BUSY_MESSAGE = (
    "The service is experiencing flaky behavior due to high load. "
    "Please try again in a few moments."
)
SERVICE_BUSY_RETRY_AFTER = 30

# Legacy fallback pricing: model -> (prompt_per_1k, completion_per_1k) in
# USD, for models not served by any deployment. Deployment-served models
# price via their provider class (providers/<name>.py, ADR-0016).
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4.1": (0.001, 0.004),
    "gpt-4.1-mini": (0.0001, 0.0004),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-20250514": (0.00025, 0.00125),
}

# Profile -> model mapping
AI_PROFILES: dict[str, str] = {
    "fast": "ollama/gemma4:12b",
    "balanced": "ollama/qwen3.6:35b-mlx",
    "premium": "gpt-4.1",
}

# In-memory usage log (session_id -> records). Persisting this is the
# natural next migration (ADR-0015).
_usage_history: dict[str, list] = {}


def _quota_sse_event(exc: HTTPException) -> str:
    """Convert a 402/429 HTTPException into an SSE event string."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    login_available = bool(detail.get("login_available"))
    if exc.status_code == 402:
        event = "credit_limit"
        message = "You've used up the free credits." + (
            " Log in to get your own free monthly quota." if login_available else ""
        )
    else:
        event = "rate_limit"
        message = (
            "You're sending requests too quickly. Please wait a moment "
            "and try again."
            + (" Or log in for higher free limits." if login_available else "")
        )
    retry_after = detail.get("retry_after")
    if exc.status_code == 429 and retry_after is None:
        retry_after = 60
    return (
        f"event: {event}\ndata: "
        + json.dumps(
            {
                "scope": "user",
                "message": message,
                "retry_after": retry_after,
                "login_available": login_available,
            }
        )
        + "\n\n"
    )


_RETRY_IN_RE = re.compile(r"retry in ([0-9.]+)s", re.IGNORECASE)
_RETRY_DELAY_RE = re.compile(r'"retryDelay":\s*"([0-9.]+)s"')


MODEL_BUSY_MESSAGE = (
    "The AI model is at its per-minute capacity. Please try again in a " "few seconds."
)


class BudgetExhausted(Exception):
    """No deployment capacity within the allowed wait (ADR-0025)."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"deployment budget exhausted, retry in {retry_after:.1f}s")
        self.retry_after = retry_after


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return (
        isinstance(exc, litellm.RateLimitError)
        or "RateLimitError" in text
        or " 429" in text
    )


def _settle_failed(holder: dict[str, Any], exc: Exception) -> None:
    """A failed call keeps its reservation (at the estimate): the provider
    counts its input tokens toward the per-minute limit even on 429/5xx."""
    holder.pop("res", None)


def _retry_hint(exc: Exception) -> float | None:
    """Provider retry delay in seconds, if the error carries one."""
    text = str(exc)
    match = _RETRY_IN_RE.search(text) or _RETRY_DELAY_RE.search(text)
    return float(match.group(1)) if match else None


def _model_rate_limit_event(retry_after: float) -> str:
    """Deployment capacity exhausted: logging in would not help."""
    seconds = 60 if math.isinf(retry_after) else max(1, math.ceil(retry_after))
    return (
        "event: rate_limit\ndata: "
        + json.dumps(
            {
                "scope": "model",
                "message": MODEL_BUSY_MESSAGE,
                "retry_after": seconds,
                "login_available": False,
            }
        )
        + "\n\n"
    )


def _too_large_event(result: TooLarge) -> str:
    message = (
        f"This JSON is about {result.doc_kb} KB; the current AI model can work "
        f"with about {result.max_kb} KB at a time. Edit one section, or "
        "continue with a trimmed copy."
    )
    return (
        "event: input_too_large\ndata: "
        + json.dumps(
            {
                "message": message,
                "doc_kb": result.doc_kb,
                "max_kb": result.max_kb,
                "sections": result.sections,
                "trimmed": result.trimmed,
            },
            default=str,
        )
        + "\n\n"
    )


_WAIT_TICK_S = 5.0


async def _acquire(
    deployment: Any, model: str, raw_estimate: int, holder: dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Reserve deployment budget for one call, waiting briefly if needed.

    Streams `waiting` events while it waits — at least every
    _WAIT_TICK_S, so the countdown updates and proxies see traffic; stores
    the reservation in holder["res"]; raises BudgetExhausted when capacity
    will not free up within deployment_budget_max_wait_s.
    """
    max_wait = get_settings().deployment_budget_max_wait_s
    # Pacing slot first (global per deployment): spreads calls over the
    # minute so they stay under the provider's cap.
    slot = budget.claim_slot(deployment, model)
    if slot > max_wait:
        raise BudgetExhausted(slot)
    while slot > 0:
        yield "event: waiting\ndata: " + json.dumps(
            {
                "retry_after": max(1, math.ceil(slot)),
                "message": "Waiting for AI model capacity…",
            }
        ) + "\n\n"
        step = min(slot, _WAIT_TICK_S)
        await asyncio.sleep(step)
        slot -= step
    waited = 0.0
    while True:
        res, wait = budget.try_reserve(deployment, model, raw_estimate)
        if res is not None:
            holder["res"] = res
            return
        if waited + wait > max_wait:
            raise BudgetExhausted(wait)
        step = min(wait, _WAIT_TICK_S)
        logger.info(
            "budget wait deployment=%s model=%s wait=%.1fs",
            getattr(deployment, "name", "?"),
            model,
            wait,
        )
        yield "event: waiting\ndata: " + json.dumps(
            {
                "retry_after": max(1, math.ceil(wait)),
                "message": "Waiting for AI model capacity…",
            }
        ) + "\n\n"
        await asyncio.sleep(step + 0.05)
        waited += step


def _transient_retry_wait(exc: Exception, attempt: int, settings: Any) -> float | None:
    """Seconds to wait before retrying an LLM call, or None to give up.

    Only short rate limits (429 with a provider hint) are retried. 5xx are
    not (ADR-0025): Google's free tier answers 500 in bursts and each retry
    adds to its per-minute count, so retries made it worse; call pacing
    keeps load down instead. LiteLLM sometimes wraps the real error
    (MidStreamFallbackError), so the message is checked too.
    """
    if attempt >= settings.chat_tool_retry_attempts:
        return None
    if _is_rate_limit(exc):
        hint = _retry_hint(exc)
        wait = hint + 0.5 if hint is not None else 5.0
        return wait if wait <= settings.chat_tool_retry_max_wait_s else None
    return None


async def _backoff(deployment: Any, model: str, wait: float) -> None:
    """Back off before a (429) retry. With a deployment budget the whole
    deployment pauses (every turn backs off, not only this one) and the next
    _acquire streams the countdown; otherwise just sleep."""
    if budget.tpm_limit(deployment) is not None:
        budget.block(deployment, model, wait)
    else:
        await asyncio.sleep(wait)


class GatewayService:
    """Single gateway class. All LLM calls flow through invoke()."""

    MODEL_PRICING = MODEL_PRICING
    AI_PROFILES = AI_PROFILES
    _usage_history = _usage_history

    @classmethod
    def _calculate_cost(
        cls,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        deployment: DeploymentProvider | None = None,
    ) -> float:
        """Calculate cost_usd from tokens + provider pricing (or fallback)."""
        if deployment is not None:
            pricing = deployment.pricing(model)
        else:
            pricing = cls.MODEL_PRICING.get(model, (0.0, 0.0))
        prompt_cost = (prompt_tokens * pricing[0]) / 1000
        completion_cost = (completion_tokens * pricing[1]) / 1000
        return round(prompt_cost + completion_cost, 6)

    @classmethod
    def _calculate_credits(cls, cost_usd: float) -> float:
        """Convert USD cost to credits. 1 credit = $0.001."""
        return round(cost_usd / 0.001, 3)

    @classmethod
    def _log_usage(
        cls, session_id: str, quota_key: str, record: dict[str, Any]
    ) -> None:
        """Append usage record to session's usage history."""
        cls._usage_history.setdefault(session_id, []).append(record)

    @classmethod
    def _resolve_model(cls, model: str | None, profile: str | None) -> str | None:
        """Explicit model, else profile mapping, else None (config default).

        None means: let DeploymentRegistry.pick_default() choose an enabled
        deployment and use its base_model.
        """
        if model:
            return model
        if profile and profile in cls.AI_PROFILES:
            return cls.AI_PROFILES[profile]
        return None

    @classmethod
    def _make_usage_event(
        cls,
        cost_usd: float,
        credits_used: float,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> str:
        """Build SSE event:usage string."""
        return (
            "event: usage\n"
            + "data: "
            + json.dumps(
                {
                    "cost_usd": cost_usd,
                    "credits_used": credits_used,
                    "model": model,
                    "provider": provider,
                    "tokens": {
                        "prompt": prompt_tokens,
                        "completion": completion_tokens,
                        "total": prompt_tokens + completion_tokens,
                    },
                }
            )
            + "\n\n"
        )

    @classmethod
    def _parse_diffs(cls, combined: str) -> list[dict[str, Any]]:
        """Parse LLM response text as a list of diff entries.

        Strips markdown code fences before parsing. Also accepts LLM
        output using key/value instead of path/old_value/new_value.
        Returns empty list if parsing fails or no valid diffs found.
        """
        import re

        diffs: list[dict[str, Any]] = []
        # Strip markdown fences: ```json ... ``` or ``` ... ```
        text = re.sub(r"^```\w*\n|\n```$", "", combined.strip())
        for candidate in (combined.strip(), text):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, list):
                    for d in parsed:
                        if not isinstance(d, dict):
                            continue
                        # Normalize LLM field-name variants
                        if "op" in d and "operation" not in d:
                            d["operation"] = d.pop("op")
                        if "value" in d and "new_value" not in d:
                            d["new_value"] = d.pop("value")
                        # Accept: path + operation (standard or normalized)
                        if "path" in d and "operation" in d:
                            diffs.append(d)
                            break
                        # Accept: key + value + operation (no path)
                        if "key" in d and "value" in d and "operation" in d:
                            entry = {
                                "path": "/" + str(d["key"]).replace(".", "/"),
                                "operation": d["operation"],
                                "old_value": d.get("value"),
                                "new_value": d["value"],
                            }
                            diffs.append(entry)
                            break
                    if diffs:
                        break
            except (json.JSONDecodeError, ValueError):
                continue
        return diffs

    @classmethod
    def _apply_diffs(
        cls, obj: dict[str, Any], diffs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply a list of diff entries to a JSON object (returns new copy)."""
        import copy

        result = copy.deepcopy(obj)
        for diff in diffs:
            path_parts = [p for p in diff.get("path", "/").split("/") if p]
            target_key = path_parts[-1] if path_parts else None
            if not target_key:
                continue
            # Navigate to parent, creating intermediate dicts as needed
            current = result
            for part in path_parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            op = diff.get("operation")
            if op == "delete":
                current.pop(target_key, None)
            else:
                current[target_key] = diff.get("new_value")
        return result

    @staticmethod
    async def invoke(
        session_id: str,
        message: str,
        principal: Principal,
        system_prompt: str,
        model: str | None = None,
        profile: str | None = None,
        reasoning: str | None = None,
        history: list[dict[str, str]] | None = None,
        toolbox: JsonToolbox | None = None,
        planner: Callable[[Any, str], TurnPlan | TooLarge] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Full LLM pipeline: credit check -> stream -> diff -> cost -> deduct -> log.

        `planner` (ADR-0025) is called once the deployment is known and
        returns the prompt plan (messages, toolbox, tool rounds) sized to
        the deployment's budget — or TooLarge, which ends the turn with an
        `input_too_large` event before any LLM call. When given, it
        replaces `system_prompt`/`history`/`toolbox`. Every LLM call
        reserves deployment budget first (waits briefly or ends with a
        model-scope `rate_limit`); user quotas are untouched by that.

        `toolbox` (documents too large to inline) enables the read-only
        search/read lookup loop on deployments with supports_tools; the
        final answer is emitted as a single `thinking` event and usage is
        summed over all rounds (ADR-0024).

        `history` is prior user/assistant messages replayed between the
        system prompt and the new message (chat history); trimmed oldest
        pair first if it would overflow the model's input window.

        `reasoning` is the per-request thinking override from the UI switch
        (None = deployment default); backends that don't support_thinking
        ignore it.
        """
        resolved_model = GatewayService._resolve_model(model, profile)
        deployment: DeploymentProvider | None = None
        # Quota errors surface as clean SSE events the client can turn into
        # a popup (with a login CTA for anonymous users), instead of leaking
        # a broken stream.
        try:
            await credit_service.check(principal)
        except HTTPException as exc:
            if exc.status_code in (402, 429):
                yield _quota_sse_event(exc)
                return
            raise

        start_time = time.monotonic()
        holder: dict[str, Any] = {}  # in-flight budget reservation
        litellm_model = ""
        try:
            # Select deployment: explicit/profile model routes via pick();
            # no model means the config default — round-robin over enabled
            # deployments, each serving its own base_model.
            if resolved_model is None:
                deployment = DeploymentRegistry.pick_default()
                resolved_model = f"{deployment.model_prefix}{deployment.base_model}"
            else:
                deployment = DeploymentRegistry.pick(resolved_model)
            litellm_model = deployment.litellm_model(resolved_model)

            logger.info(
                "invoke session=%s model=%s deployment=%s principal=%s",
                session_id,
                resolved_model,
                deployment.name,
                mask_secret(principal.quota_key),
            )
            logger.debug(
                "invoke request session=%s litellm_model=%s base_url=%s "
                "system_prompt=%s user_message=%r",
                session_id,
                litellm_model,
                deployment.base_url,
                system_prompt,
                message,
            )

            # Emit deployment selection event
            yield "event: deployment\ndata: " + json.dumps(
                {
                    "model": resolved_model,
                    "deployment": deployment.name,
                    "provider": deployment.model_prefix,
                }
            ) + "\n\n"

            settings = get_settings()
            max_rounds = settings.chat_tool_max_rounds
            raw_estimate = 0
            if planner is not None:
                plan = planner(deployment, litellm_model)
                if isinstance(plan, TooLarge):
                    yield _too_large_event(plan)
                    return
                messages = plan.messages
                toolbox = plan.toolbox
                max_rounds = plan.max_rounds
                raw_estimate = plan.raw_estimate
            else:
                messages = chat_history_service.fit_to_context(
                    litellm_model,
                    system_prompt,
                    list(history or []),
                    message,
                    reserve_output=settings.llm_max_tokens,
                )
            use_tools = (
                toolbox is not None
                and settings.chat_tools_enabled
                and deployment.supports_tools
            )
            if use_tools:
                usage: dict[str, int] = {"prompt": 0, "completion": 0}
                async for event_text in GatewayService._tool_loop(
                    session_id,
                    litellm_model,
                    deployment,
                    messages,
                    toolbox,
                    usage,
                    deployment.completion_params(resolved_model, reasoning),
                    max_rounds=max_rounds,
                    holder=holder,
                ):
                    yield event_text
                prompt_tokens = usage["prompt"]
                completion_tokens = usage["completion"]
                logger.info(
                    "invoke session=%s usage=%s",
                    session_id,
                    {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    },
                )
                cost_usd = GatewayService._calculate_cost(
                    prompt_tokens, completion_tokens, resolved_model, deployment
                )
            else:
                if budget.tpm_limit(deployment) is not None:
                    raw_estimate = raw_estimate or budget.estimate_tokens(
                        litellm_model, messages
                    )
                # Retry a short 429 only before any text reached the client —
                # a retry after that would repeat it. 5xx are not retried.
                attempt = 0
                while True:
                    async for event_text in _acquire(
                        deployment, litellm_model, raw_estimate, holder
                    ):
                        yield event_text
                    content_parts: list[str] = []
                    last_chunk = None
                    try:
                        response = await litellm.acompletion(
                            model=litellm_model,
                            base_url=deployment.base_url,
                            api_key=deployment.api_key or None,
                            messages=messages,
                            stream=True,
                            timeout=120.0,
                            num_retries=0,
                            max_tokens=get_settings().llm_max_tokens,
                            stream_options={"include_usage": True},
                            **deployment.completion_params(resolved_model, reasoning),
                        )
                        async for chunk in response:
                            last_chunk = chunk
                            if not getattr(chunk, "choices", None):
                                continue
                            delta = chunk.choices[0].delta
                            if isinstance(delta, dict):
                                text = delta.get("content")
                            else:
                                text = getattr(delta, "content", None)
                            if text:
                                content_parts.append(text)
                                yield "event: thinking\ndata: " + json.dumps(
                                    {"text": text}
                                ) + "\n\n"
                        break
                    except Exception as exc:
                        wait = (
                            None
                            if content_parts
                            else _transient_retry_wait(exc, attempt, settings)
                        )
                        if wait is None:
                            raise
                        _settle_failed(holder, exc)
                        attempt += 1
                        logger.warning(
                            "invoke session=%s transient error, retry %d in %.1fs: %s",
                            session_id,
                            attempt,
                            wait,
                            type(exc).__name__,
                        )
                        await _backoff(deployment, litellm_model, wait)

                combined = "".join(content_parts)
                logger.info(
                    "invoke session=%s response_len=%d", session_id, len(combined)
                )
                logger.debug(
                    "invoke response (full) session=%s: %s", session_id, combined
                )

                # Extract usage from last streaming chunk.
                # litellm streaming: usage is on each chunk (Usage pydantic model),
                # not on the response wrapper. Last chunk has the full token counts.
                prompt_tokens = 0
                completion_tokens = 0
                model_name = resolved_model
                cost_usd = 0.0
                if last_chunk is not None:
                    chunk_usage = getattr(last_chunk, "usage", None)
                    if chunk_usage is not None:
                        if isinstance(chunk_usage, dict):
                            prompt_tokens = chunk_usage.get("prompt_tokens", 0) or 0
                            completion_tokens = (
                                chunk_usage.get("completion_tokens", 0) or 0
                            )
                            model_name = chunk_usage.get("model", resolved_model)
                            cost_usd = chunk_usage.get("response_cost")
                        else:
                            # chunk_usage is a pydantic model (Usage)
                            try:
                                usage_dict = vars(chunk_usage)
                                prompt_tokens = usage_dict.get("prompt_tokens", 0) or 0
                                completion_tokens = (
                                    usage_dict.get("completion_tokens", 0) or 0
                                )
                                model_name = usage_dict.get("model", resolved_model)
                                cost_usd = usage_dict.get("response_cost")
                            except Exception:
                                pass
                        logger.info(
                            "invoke session=%s usage=%s",
                            session_id,
                            {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                            },
                        )

                    if cost_usd is None or cost_usd == 0:
                        cost_usd = GatewayService._calculate_cost(
                            prompt_tokens,
                            completion_tokens,
                            model_name or resolved_model,
                            deployment,
                        )
                else:
                    # No chunks received — fallback to zero
                    cost_usd = GatewayService._calculate_cost(
                        0, 0, resolved_model, deployment
                    )
                if holder.get("res") is not None:
                    budget.settle(holder.pop("res"), prompt_tokens)

            credits_used = GatewayService._calculate_credits(cost_usd)
            latency_ms = int((time.monotonic() - start_time) * 1000)

            logger.info(
                "invoke session=%s cost_usd=%.6f credits=%.3f latency_ms=%d "
                "prompt_tokens=%d completion_tokens=%d",
                session_id,
                cost_usd,
                credits_used,
                latency_ms,
                prompt_tokens,
                completion_tokens,
            )

            # Emit usage event before complete
            yield GatewayService._make_usage_event(
                cost_usd,
                credits_used,
                resolved_model,
                deployment.name,
                prompt_tokens,
                completion_tokens,
            )

            # Deduct credits and log
            total_tokens = prompt_tokens + completion_tokens
            await credit_service.deduct(principal, credits_used, total_tokens)
            GatewayService._log_usage(
                session_id,
                principal.quota_key,
                {
                    "request_id": uuid.uuid4().hex,
                    "quota_key": principal.quota_key,
                    "session_id": session_id,
                    "model": resolved_model,
                    "provider": deployment.name,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "cost_usd": cost_usd,
                    "credits_used": credits_used,
                    "latency_ms": latency_ms,
                    "feature": "modify-json",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        except BudgetExhausted as e:
            # Not a provider error: nothing was sent, user quota untouched.
            logger.warning(
                "invoke session=%s deployment=%s budget exhausted retry_after=%.1fs",
                session_id,
                deployment.name if deployment else "?",
                e.retry_after,
            )
            yield _model_rate_limit_event(e.retry_after)
        except Exception as e:
            _settle_failed(holder, e)
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "invoke session=%s model=%s error=%s latency_ms=%d",
                session_id,
                resolved_model or "auto",
                str(e),
                latency_ms,
            )
            # Log failed usage record
            GatewayService._log_usage(
                session_id,
                principal.quota_key,
                {
                    "request_id": uuid.uuid4().hex,
                    "quota_key": principal.quota_key,
                    "session_id": session_id,
                    "model": resolved_model or "auto",
                    "provider": deployment.name if deployment else "unknown",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "credits_used": 0.0,
                    "latency_ms": latency_ms,
                    "feature": "modify-json",
                    "status": "failed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            if deployment is not None and _is_rate_limit(e):
                # Provider 429 (ADR-0025): model capacity, with its real retry
                # delay — not "high load", and logging in would not help.
                hint = _retry_hint(e)
                retry_after = hint if hint is not None else 60.0
                budget.block(deployment, litellm_model, retry_after)
                yield _model_rate_limit_event(retry_after)
                return
            # Deployment/provider failure -> friendly popup event; raw error
            # stays in the logs above.
            yield "event: service_unavailable\ndata: " + json.dumps(
                {
                    "scope": "model",
                    "message": SERVICE_BUSY_MESSAGE,
                    "retry_after": SERVICE_BUSY_RETRY_AFTER,
                }
            ) + "\n\n"

    @staticmethod
    async def _tool_loop(
        session_id: str,
        litellm_model: str,
        deployment: DeploymentProvider,
        messages: list[dict[str, Any]],
        toolbox: JsonToolbox,
        usage: dict[str, int],
        extra_params: dict[str, Any],
        max_rounds: int | None = None,
        holder: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Non-streaming rounds: model calls search/read until it answers.

        Tool results go back as `tool` messages; each call is surfaced as a
        `tool` SSE event (progress only — chat_service ignores it). After
        chat_tool_max_rounds, or past the turn deadline, the model is told to
        answer now. The final content is yielded as one `thinking` event so
        the existing parse/apply path is unchanged.

        `max_rounds` comes from the turn planner (ADR-0025) when the
        deployment has a budget; each round reserves budget for its own
        (growing) prompt and settles with the provider's count.
        """
        settings = get_settings()
        messages = list(messages)
        messages[0] = {
            **messages[0],
            "content": messages[0]["content"] + "\n\n" + JsonToolbox.INSTRUCTIONS,
        }
        deadline = time.monotonic() + settings.chat_tool_turn_timeout_s
        tool_model = (
            deployment.tool_litellm_model(litellm_model)
            if hasattr(deployment, "tool_litellm_model")
            else litellm_model
        )
        if max_rounds is None:
            max_rounds = settings.chat_tool_max_rounds
        max_rounds = max(0, max_rounds)
        if holder is None:
            holder = {}
        has_budget = budget.tpm_limit(deployment) is not None
        content = ""
        round_no = 0
        for round_no in range(max_rounds + 1):
            final = round_no == max_rounds or time.monotonic() > deadline
            if final and round_no > 0:
                messages.append(
                    {
                        "role": "user",
                        "content": "Tool budget used up. Reply NOW with the final "
                        "single JSON object; do not call tools.",
                    }
                )
            request = dict(
                model=tool_model,
                base_url=deployment.base_url,
                api_key=deployment.api_key or None,
                messages=messages,
                tools=JsonToolbox.schemas(),
                timeout=120.0,
                num_retries=0,
                max_tokens=settings.llm_max_tokens,
                **extra_params,
            )
            # Retry THIS round on transient provider errors (ADR-0024,
            # relaxes ADR-0007 inside the loop): nothing has reached the user
            # as an answer yet, and re-running one round is far cheaper than
            # failing — or re-running — the whole multi-round turn.
            attempt = 0
            while True:
                raw = (
                    budget.estimate_tokens(litellm_model, messages) if has_budget else 0
                )
                async for event_text in _acquire(
                    deployment, litellm_model, raw, holder
                ):
                    yield event_text
                try:
                    if getattr(deployment, "tool_streaming", True):
                        # Stream by default: text goes out live as `draft` events
                        # (keeps proxies like Cloudflare from idling out; not parsed
                        # as the answer, since the round may still end in a tool
                        # call), tool-call fragments are rebuilt at the end.
                        chunks: list[Any] = []
                        stream = await litellm.acompletion(
                            stream=True,
                            stream_options={"include_usage": True},
                            **request,
                        )
                        async for chunk in stream:
                            chunks.append(chunk)
                            if not getattr(chunk, "choices", None):
                                continue
                            delta = chunk.choices[0].delta
                            text = getattr(delta, "content", None)
                            if text:
                                yield "event: draft\ndata: " + json.dumps(
                                    {"text": text}
                                ) + "\n\n"
                        response = litellm.stream_chunk_builder(
                            chunks, messages=messages
                        )
                        if response is None:
                            raise RuntimeError("empty streamed tool response")
                    else:
                        response = await litellm.acompletion(stream=False, **request)
                    break
                except Exception as exc:
                    _settle_failed(holder, exc)
                    wait = _transient_retry_wait(exc, attempt, settings)
                    if wait is None:
                        raise
                    attempt += 1
                    logger.warning(
                        "tool loop session=%s round=%d transient error, retry %d in %.1fs: %s",
                        session_id,
                        round_no + 1,
                        attempt,
                        wait,
                        type(exc).__name__,
                    )
                    await _backoff(deployment, litellm_model, wait)
            u = getattr(response, "usage", None)
            if holder.get("res") is not None:
                budget.settle(
                    holder.pop("res"), int(getattr(u, "prompt_tokens", 0) or 0)
                )
            usage["prompt"] += int(getattr(u, "prompt_tokens", 0) or 0)
            usage["completion"] += int(getattr(u, "completion_tokens", 0) or 0)
            message = response.choices[0].message
            calls = list(getattr(message, "tool_calls", None) or [])
            content = message.content or ""
            if not calls or final:
                if calls:
                    logger.warning(
                        "tool loop session=%s model still calling tools at final round",
                        session_id,
                    )
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.function.name,
                                "arguments": c.function.arguments,
                            },
                        }
                        for c in calls
                    ],
                }
            )
            for c in calls:
                result = toolbox.call(c.function.name, c.function.arguments)
                logger.info(
                    "tool call session=%s round=%d name=%s args=%s result_chars=%d",
                    session_id,
                    round_no + 1,
                    c.function.name,
                    str(c.function.arguments)[:200],
                    len(result),
                )
                logger.debug("tool result session=%s %s", session_id, result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.id,
                        "name": c.function.name,
                        "content": result,
                    }
                )
                yield "event: tool\ndata: " + json.dumps(
                    {
                        "round": round_no + 1,
                        "name": c.function.name,
                        "args": str(c.function.arguments)[:200],
                        "result_chars": len(result),
                    }
                ) + "\n\n"
        logger.info(
            "tool loop session=%s rounds=%d answer_len=%d",
            session_id,
            round_no + 1,
            len(content),
        )
        if content:
            yield "event: thinking\ndata: " + json.dumps({"text": content}) + "\n\n"

    @classmethod
    async def explain(
        cls,
        session_id: str,
        principal: Principal,
        working_json: dict[str, Any],
    ) -> str:
        """Explain a JSON document. Calls LLM, collects response, returns markdown.

        Non-streaming path: quota errors propagate as HTTPException 402/429
        with a structured detail dict (login_available, retry_after).
        """
        from .prompting import EXPLAIN_TEMPLATE

        await credit_service.check(principal)

        # No explicit model on this path: use the config default.
        deployment = DeploymentRegistry.pick_default()
        resolved_model = f"{deployment.model_prefix}{deployment.base_model}"
        litellm_model = deployment.litellm_model(resolved_model)

        system_prompt = EXPLAIN_TEMPLATE
        logger.info(
            "explain invoke session=%s model=%s deployment=%s principal=%s working_keys=%d",
            session_id,
            resolved_model,
            deployment.name,
            mask_secret(principal.quota_key),
            len(working_json),
        )
        logger.debug(
            "explain request session=%s working_json=%s", session_id, working_json
        )

        content_parts: list[str] = []
        last_chunk = None

        response = await litellm.acompletion(
            model=litellm_model,
            base_url=deployment.base_url,
            api_key=deployment.api_key or None,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Here is the JSON to explain:\n"
                    + json.dumps(working_json, indent=2),
                },
            ],
            stream=True,
            timeout=120.0,
            num_retries=0,
            max_tokens=get_settings().llm_max_tokens,
            stream_options={"include_usage": True},
            **deployment.completion_params(resolved_model),
        )
        async for chunk in response:
            last_chunk = chunk
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            if isinstance(delta, dict):
                text = delta.get("content")
            else:
                text = getattr(delta, "content", None)
            if text:
                content_parts.append(text)

        combined = "".join(content_parts)

        # Usage tracking (same pattern as invoke)
        prompt_tokens = 0
        completion_tokens = 0
        if last_chunk is not None:
            chunk_usage = getattr(last_chunk, "usage", None)
            if chunk_usage is not None:
                if isinstance(chunk_usage, dict):
                    prompt_tokens = chunk_usage.get("prompt_tokens", 0) or 0
                    completion_tokens = chunk_usage.get("completion_tokens", 0) or 0
                else:
                    try:
                        usage_dict = vars(chunk_usage)
                        prompt_tokens = usage_dict.get("prompt_tokens", 0) or 0
                        completion_tokens = usage_dict.get("completion_tokens", 0) or 0
                    except Exception:
                        pass

        logger.info(
            "explain finished session=%s response_len=%d prompt_tokens=%d completion_tokens=%d",
            session_id,
            len(combined),
            prompt_tokens,
            completion_tokens,
        )
        logger.debug("explain response (full) session=%s: %s", session_id, combined)

        cost_usd = cls._calculate_cost(
            prompt_tokens, completion_tokens, resolved_model, deployment
        )
        credits_used = cls._calculate_credits(cost_usd)
        total_tokens = prompt_tokens + completion_tokens
        await credit_service.deduct(principal, credits_used, total_tokens)
        cls._log_usage(
            session_id,
            principal.quota_key,
            {
                "request_id": uuid.uuid4().hex,
                "quota_key": principal.quota_key,
                "session_id": session_id,
                "model": resolved_model,
                "provider": deployment.name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "credits_used": credits_used,
                "feature": "explain-json",
                "status": "success",
            },
        )

        return combined

    @classmethod
    def get_usage(cls, session_id: str) -> list[dict[str, Any]]:
        """Return usage records for a session. For future GET /api/usage."""
        return cls._usage_history.get(session_id, [])
