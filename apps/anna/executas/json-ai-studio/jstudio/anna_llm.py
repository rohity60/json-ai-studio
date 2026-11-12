"""litellm custom provider ``anna/`` — completions via Anna sampling.

The shared gateway calls ``litellm.acompletion(model="anna/default", …)``
exactly as it does for any provider. This handler turns that call into a
``sampling/createMessage`` request to the Anna host, which runs the
signed-in user's own model and bills their Anna plan. No API key exists
on our side.

Host limits per tool invoke: 8 calls, 32,000 tokens in total, 8,192
output tokens per call, 64 messages.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import litellm
from litellm import CustomLLM
from litellm.types.utils import GenericStreamingChunk

from .rpc import HostError, HostRpc, current_invoke_id, host

logger = logging.getLogger("jstudio.anna_llm")

MAX_OUTPUT_TOKENS = 8192
MAX_MESSAGES = 64
SAMPLING_TIMEOUT_S = 120.0

QUOTA_EXCEEDED = -32002
MAX_CALLS_EXCEEDED = -32006
MAX_TOKENS_EXCEEDED = -32007

# Last host error per invoke, so the tool layer can explain a failed turn
# in Anna's terms (the gateway only reports a generic failure).
_last_error: dict[str, HostError] = {}


def take_last_error(invoke_id: str | None) -> HostError | None:
    return _last_error.pop(invoke_id or "", None)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # OpenAI content parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return "" if content is None else str(content)


def to_sampling_params(
    messages: list[dict[str, Any]], optional_params: dict[str, Any]
) -> dict[str, Any]:
    """OpenAI-style chat request → ``sampling/createMessage`` params."""
    system: list[str] = []
    turns: list[dict[str, Any]] = []
    for m in messages:
        role, text = m.get("role"), _text(m.get("content"))
        if role == "system":
            system.append(text)
        elif role in ("user", "assistant"):
            turns.append({"role": role, "content": {"type": "text", "text": text}})
    if len(turns) > MAX_MESSAGES:
        turns = turns[-MAX_MESSAGES:]

    requested = optional_params.get("max_tokens") or MAX_OUTPUT_TOKENS
    params: dict[str, Any] = {
        "messages": turns,
        "maxTokens": min(int(requested), MAX_OUTPUT_TOKENS),
        "includeContext": "none",
    }
    if system:
        params["systemPrompt"] = "\n\n".join(system)
    invoke_id = current_invoke_id()
    if invoke_id:
        params["metadata"] = {"executa_invoke_id": invoke_id}

    # Always explicit: reasoning tokens count inside maxTokens on Anna.
    thinking = optional_params.get("anna_thinking", False)
    params["thinking"] = {"effort": thinking} if isinstance(thinking, str) else False
    return params


class AnnaSamplingLLM(CustomLLM):
    def __init__(self, rpc: HostRpc | None = None) -> None:
        super().__init__()
        self._rpc = rpc or host

    async def _sample(
        self, messages: list[dict[str, Any]], optional_params: dict[str, Any]
    ) -> tuple[str, dict[str, int], str]:
        params = to_sampling_params(messages, optional_params or {})
        try:
            result = await self._rpc.call(
                "sampling/createMessage", params, timeout=SAMPLING_TIMEOUT_S
            )
        except HostError as exc:
            _last_error[current_invoke_id() or ""] = exc
            logger.warning("sampling failed code=%s message=%s", exc.code, exc.message)
            raise
        text = _text((result.get("content") or {}).get("text"))
        usage = result.get("usage") or {}
        prompt = int(usage.get("inputTokens") or 0)
        completion = int(usage.get("outputTokens") or 0)
        if not text and result.get("stopReason") == "maxTokens":
            logger.warning(
                "sampling returned no text at maxTokens (reasoning=%s)",
                usage.get("reasoningTokens"),
            )
        return (
            text,
            {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": int(usage.get("totalTokens") or prompt + completion),
            },
            str(result.get("model") or "anna/default"),
        )

    async def acompletion(self, *args, **kwargs) -> litellm.ModelResponse:
        text, usage, model = await self._sample(
            kwargs.get("messages") or [], kwargs.get("optional_params") or {}
        )
        return litellm.ModelResponse(
            model=model,
            choices=[
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text},
                }
            ],
            usage=usage,
        )

    async def astreaming(self, *args, **kwargs) -> AsyncIterator[GenericStreamingChunk]:
        # Sampling is one request → one response: emit it as a single chunk.
        text, usage, _model = await self._sample(
            kwargs.get("messages") or [], kwargs.get("optional_params") or {}
        )
        yield GenericStreamingChunk(
            text=text,
            is_finished=True,
            finish_reason="stop",
            index=0,
            tool_use=None,
            usage=usage,
        )


def register(rpc: HostRpc | None = None) -> AnnaSamplingLLM:
    """Install the handler under the ``anna/`` prefix."""
    handler = AnnaSamplingLLM(rpc)
    others = [
        p for p in (litellm.custom_provider_map or []) if p.get("provider") != "anna"
    ]
    litellm.custom_provider_map = [
        *others,
        {"provider": "anna", "custom_handler": handler},
    ]
    return handler
