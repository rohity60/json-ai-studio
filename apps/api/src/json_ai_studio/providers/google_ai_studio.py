"""Google AI Studio provider — Gemini/Gemma family."""

from __future__ import annotations

from typing import Any, ClassVar

from .base import DeploymentProvider


class GoogleAIStudioProvider(DeploymentProvider):
    name = "google_ai_studio"
    model_prefix = "gemini/"
    api_key_setting = "google_ai_studio_api_key"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    PRICING = {
        # Gemma models are free tier on AI Studio.
        "gemma-4-26b-a4b-it": (0.0, 0.0),
        "gemini-2.0-flash": (0.0001, 0.0003),
    }

    # Generic reasoning level -> generationConfig.thinkingConfig.thinkingLevel.
    # Gemma 4 rejects OpenAI-style reasoning_effort (UnsupportedParamsError)
    # and 500s without a thinkingConfig; litellm passes the thinkingConfig
    # kwarg through to the API.
    _THINKING_LEVELS: ClassVar[dict[str, str]] = {
        "none": "MINIMAL",
        "minimal": "MINIMAL",
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
    }

    def completion_params(
        self, model: str, reasoning: str | None = None
    ) -> dict[str, Any]:
        level = self.resolve_reasoning(reasoning)
        if level is None:
            return {}
        mapped = self._THINKING_LEVELS.get(level.lower(), level.upper())
        return {"thinkingConfig": {"thinkingLevel": mapped}}
