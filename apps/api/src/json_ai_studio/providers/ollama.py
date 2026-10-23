"""Ollama provider — self-hosted models.

Endpoint comes from Settings.ollama_base_url (env OLLAMA_BASE_URL), e.g.
http://localhost:11434 locally or a tunnel/hosted URL in production.
No hardcoded default: when unset, the deployment is disabled at load.
"""

from __future__ import annotations

from typing import Any

from ..settings import Settings, get_settings
from .base import DeploymentProvider


class OllamaProvider(DeploymentProvider):
    name = "ollama_local"
    model_prefix = "ollama/"
    api_key_setting = None
    PRICING = {
        "qwen3.6:35b-mlx": (0.0, 0.0),
        "gemma4:12b": (0.001, 0.003),
    }

    def _resolve_base_url(self, cfg: dict[str, Any], settings: Settings) -> str:
        return settings.ollama_base_url or ""

    def tool_litellm_model(self, litellm_model: str) -> str:
        """Use Ollama's chat API for tool rounds. LiteLLM's ``ollama/``
        (generate) route lost native tool calls once the system prompt was
        long (gemma4:12b, 2026-10-23: 0 calls on the full prompt via
        ``ollama/``, a correct ``search`` call via ``ollama_chat/``)."""
        if litellm_model.startswith("ollama/"):
            return "ollama_chat/" + litellm_model[len("ollama/") :]
        return litellm_model

    def completion_params(
        self, model: str, reasoning: str | None = None
    ) -> dict[str, Any]:
        """Ollama-native controls instead of OpenAI reasoning_effort.

        - ``think``: Ollama runs thinking-capable models (Gemma 4, Qwen 3)
          with thinking ON unless told otherwise; with reasoning "none" that
          used to burn the whole timeout on hidden thinking and return no
          content. Map the generic level to an explicit on/off.
        - ``num_ctx``: Ollama's default context window is small and silently
          truncates long prompts (system prompt + history); set it.
        """
        level = self.resolve_reasoning(reasoning)
        return {
            "think": not (level is None or level.lower() == "none"),
            "num_ctx": get_settings().ollama_num_ctx,
        }
