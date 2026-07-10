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

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import litellm
from fastapi import HTTPException

from .auth import Principal
from .deployment import DeploymentRegistry
from .providers import DeploymentProvider
from .services import credit_service

logger = logging.getLogger("json_ai_studio.gateway")

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
                "scope": "model",
                "message": message,
                "retry_after": retry_after,
                "login_available": login_available,
            }
        )
        + "\n\n"
    )


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
    ) -> AsyncGenerator[str, None]:
        """Full LLM pipeline: credit check -> stream -> diff -> cost -> deduct -> log."""
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
                principal.quota_key[:24],
            )

            # Emit deployment selection event
            yield "event: deployment\ndata: " + json.dumps(
                {
                    "model": resolved_model,
                    "deployment": deployment.name,
                    "provider": deployment.model_prefix,
                }
            ) + "\n\n"

            response = await litellm.acompletion(
                model=litellm_model,
                base_url=deployment.base_url,
                api_key=deployment.api_key or None,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                stream=True,
                timeout=120.0,
                stream_options={"include_usage": True},
                **deployment.completion_params(resolved_model),
            )

            content_parts: list[str] = []
            last_chunk = None
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

            combined = "".join(content_parts)
            logger.info("invoke session=%s response_len=%d", session_id, len(combined))

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
                        completion_tokens = chunk_usage.get("completion_tokens", 0) or 0
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

        except Exception as e:
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
            yield "event: error\ndata: " + json.dumps(
                {"error": str(e), "latency_ms": latency_ms}
            ) + "\n\n"

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
