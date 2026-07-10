"""Ollama provider — self-hosted models.

Endpoint comes from Settings.ollama_base_url (env OLLAMA_BASE_URL), e.g.
http://localhost:11434 locally or a tunnel/hosted URL in production.
No hardcoded default: when unset, the deployment is disabled at load.
"""

from __future__ import annotations

from typing import Any

from ..settings import Settings
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
