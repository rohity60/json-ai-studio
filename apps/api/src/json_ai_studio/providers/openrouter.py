"""OpenRouter provider — aggregated multi-provider API."""

from __future__ import annotations

from .base import DeploymentProvider


class OpenRouterProvider(DeploymentProvider):
    name = "openrouter"
    model_prefix = "openrouter/"
    api_key_setting = "openrouter_api_key"
    default_base_url = "https://openrouter.ai/api/v1"
    # Pricing varies per routed backend; unknown models cost 0.0.
    PRICING: dict[str, tuple[float, float]] = {}
