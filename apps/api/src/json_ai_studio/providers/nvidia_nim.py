"""NVIDIA NIM provider — GPU-accelerated inference API."""

from __future__ import annotations

from typing import Any

from .base import DeploymentProvider


class NvidiaNimProvider(DeploymentProvider):
    name = "nvidia_nim"
    model_prefix = "nvidia_nim/"
    api_key_setting = "nvidia_nim_api_key"
    default_base_url = "https://integrate.api.nvidia.com/v1"
    # No published per-token pricing wired yet; unknown models cost 0.0.
    PRICING: dict[str, tuple[float, float]] = {}

    # NIM's vLLM backend rejects OpenAI-style reasoning_effort
    # (UnsupportedParamsError) for Gemma; thinking is toggled via
    # chat_template_kwargs.enable_thinking instead.
    def completion_params(self, model: str) -> dict[str, Any]:
        if self.reasoning is None:
            return {}
        enable_thinking = self.reasoning.lower() not in ("none", "minimal")
        return {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
