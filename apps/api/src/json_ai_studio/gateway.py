"""AI Gateway — cost calculation, credit tracking, usage logging.

Centralized LiteLLM integration. All LLM calls flow through GatewayService.
Calculates cost from token counts, deducts credits, logs usage.
Emits SSE events: thinking -> diff(s) -> usage -> complete.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import litellm
from fastapi import HTTPException
from openai.types.responses.responses_client_event_param import StreamOptions

logger = logging.getLogger("json_ai_studio.gateway")

# Pricing: model -> (prompt_per_1k, completion_per_1k) in USD
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "ollama/qwen3.6:35b-mlx": (0.0, 0.0),
    "ollama/gemma4:12b": (0.001, 0.003),
    "gpt-4.1": (0.001, 0.004),
    "gpt-4.1-mini": (0.0001, 0.0004),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-20250514": (0.00025, 0.00125),
    "gemini-2.0-flash": (0.0001, 0.0003),
}

# Profile -> model mapping
AI_PROFILES: dict[str, str] = {
    "fast": "ollama/gemma4:12b",
    "balanced": "ollama/qwen3.6:35b-mlx",
    "premium": "gpt-4.1",
}

# In-memory state
_user_credits: dict[str, dict[str, Any]] = {}  # api_key -> credit record
_usage_history: dict[str, list] = {}  # session_id -> usage records
_per_minute_credits: dict[str, deque] = (
    {}
)  # api_key -> deque of (timestamp, token_count)


class GatewayService:
    """Single gateway class. All LLM calls flow through invoke()."""

    _per_minute_credits = _per_minute_credits
    MODEL_PRICING = MODEL_PRICING
    AI_PROFILES = AI_PROFILES
    _user_credits = _user_credits
    _usage_history = _usage_history

    @classmethod
    def _ensure_credits(cls, api_key: str) -> dict[str, Any]:
        """Create default credit record for unknown API key."""
        if api_key not in cls._user_credits:
            if api_key == "dev-default-key":
                cls._user_credits[api_key] = {
                    "plan": "free",
                    "monthly_limit": 10000,
                    "per_min_credits": 40,
                    "credits_used": 0,
                    "billing_cycle_start": datetime.now(timezone.utc).isoformat(),
                }
            else:
                cls._user_credits[api_key] = {
                    "plan": "free",
                    "monthly_limit": 100,
                    "credits_used": 0,
                    "billing_cycle_start": datetime.now(timezone.utc).isoformat(),
                }

    @classmethod
    def _check_credits(cls, api_key: str) -> None:
        """Raise HTTPException(402) if credits exhausted."""
        credits: dict[str, Any] | None = cls._user_credits.get(api_key)
        if credits is None:
            return
        # Monthly check
        if (
            credits["monthly_limit"] != -1
            and credits["credits_used"] >= credits["monthly_limit"]
        ):
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Insufficient credits",
                    "hint": "Upgrade your plan. Current balance: 0 credits.",
                    "required": 0,
                    "current_balance": 0,
                },
            )
        # Per-minute token-sum check (sliding window)
        now = time.monotonic()
        window_start = now - 60
        tokens_q = cls._per_minute_credits.get(api_key)
        if tokens_q is None:
            tokens_q = deque()
            cls._per_minute_credits[api_key] = tokens_q
        # Prune old entries outside 60s window
        while tokens_q and tokens_q[0][0] < window_start:
            tokens_q.popleft()
        # Sum tokens in window
        total_tokens = sum(tc for _, tc in tokens_q)
        # Log current window token usage
        logger.error("per_minute_tokens key=%s tokens=%d limit", api_key, total_tokens)
        # Cap: 10000 tokens per minute for default key
        if api_key == "dev-default-key":
            if total_tokens >= credits.get("per_min_credits", 0):
                raise HTTPException(
                    status_code=429,
                    detail="Per-minute token limit exceeded",
                )

    @classmethod
    def _calculate_cost(
        cls, prompt_tokens: int, completion_tokens: int, model: str
    ) -> float:
        """Calculate cost_usd from tokens + pricing table."""
        pricing = cls.MODEL_PRICING.get(model, (0.0, 0.0))
        prompt_cost = (prompt_tokens * pricing[0]) / 1000
        completion_cost = (completion_tokens * pricing[1]) / 1000
        return round(prompt_cost + completion_cost, 6)

    @classmethod
    def _calculate_credits(cls, cost_usd: float) -> float:
        """Convert USD cost to credits. 1 credit = $0.001."""
        return round(cost_usd / 0.001, 3)

    @classmethod
    def _deduct_credits(cls, api_key: str, credits: float, tokens: int = 0) -> None:
        """Subtract credits from API key's monthly balance."""
        record = cls._user_credits.get(api_key)
        if record is None:
            return
        now = datetime.now(timezone.utc)
        cycle_start_str = record.get("billing_cycle_start", "")
        try:
            cycle_start = datetime.fromisoformat(cycle_start_str)
            if (now - cycle_start).total_seconds() > 30 * 86400:
                record["credits_used"] = 0
                record["billing_cycle_start"] = now.isoformat()
        except (ValueError, TypeError):
            pass
        record["credits_used"] = record.get("credits_used", 0) + credits
        # Track tokens for per-minute sliding window
        if api_key == "dev-default-key" and tokens > 0:
            cls._per_minute_credits.setdefault(api_key, deque()).append(
                (time.monotonic(), credits)
            )

    @classmethod
    def _log_usage(cls, session_id: str, api_key: str, record: dict[str, Any]) -> None:
        """Append usage record to session's usage history."""
        cls._usage_history.setdefault(session_id, []).append(record)

    @classmethod
    def _resolve_model(cls, model: str | None, profile: str | None) -> str:
        """Resolve model from explicit param or profile mapping."""
        if model:
            return model
        if profile and profile in cls.AI_PROFILES:
            return cls.AI_PROFILES[profile]
        return "ollama/gemma4:12b"

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
        api_key: str,
        system_prompt: str,
        model: str | None = None,
        profile: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Full LLM pipeline: credit check -> stream -> diff -> cost -> deduct -> log."""
        resolved_model = GatewayService._resolve_model(model, profile)
        GatewayService._ensure_credits(api_key)
        GatewayService._check_credits(api_key)

        logger.info(
            "invoke session=%s model=%s api_key=%s",
            session_id,
            resolved_model,
            api_key[:8] + "...",
        )

        start_time = time.monotonic()
        try:
            response = await litellm.acompletion(
                model=resolved_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                stream=True,
                timeout=120.0,
                stream_options={"include_usage": True},
            )

            content_parts: list[str] = []
            last_chunk = None
            async for chunk in response:
                last_chunk = chunk
                text = chunk.choices[0].delta.get("content")
                if text:
                    content_parts.append(text)
                    yield "event: thinking\ndata" + json.dumps({"text": text}) + "\n\n"

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
                        prompt_tokens, completion_tokens, model_name or resolved_model
                    )
            else:
                # No chunks received — fallback to zero
                cost_usd = GatewayService._calculate_cost(0, 0, resolved_model)

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
                "ollama",
                prompt_tokens,
                completion_tokens,
            )

            # Deduct credits and log
            total_tokens = prompt_tokens + completion_tokens
            GatewayService._deduct_credits(api_key, credits_used, total_tokens)
            GatewayService._log_usage(
                session_id,
                api_key,
                {
                    "request_id": uuid.uuid4().hex,
                    "api_key": api_key,
                    "session_id": session_id,
                    "model": resolved_model,
                    "provider": "ollama",
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
                resolved_model,
                str(e),
                latency_ms,
            )
            # Log failed usage record
            GatewayService._log_usage(
                session_id,
                api_key,
                {
                    "request_id": uuid.uuid4().hex,
                    "api_key": api_key,
                    "session_id": session_id,
                    "model": resolved_model,
                    "provider": "ollama",
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
            yield "event: error\ndata" + json.dumps(
                {"error": str(e), "latency_ms": latency_ms}
            ) + "\n\n"

    @classmethod
    def get_usage(cls, session_id: str) -> list[dict[str, Any]]:
        """Return usage records for a session. For future GET /api/usage."""
        return cls._usage_history.get(session_id, [])

    @classmethod
    def get_user_credits(cls, api_key: str) -> dict[str, Any]:
        """Return credit record for an API key. For future GET /api/credits."""
        return cls._user_credits.get(api_key, {})
