"""Anna provider — LLM calls served by the Anna host (ADR-0028).

Inside the Anna App's Executa there are no provider keys: completions go
to the Anna host over sampling reverse-RPC, billed to the signed-in Anna
user. The transport is a litellm custom provider registered under the
``anna/`` prefix by the Executa (``litellm.custom_provider_map``); the
gateway, turn planner and tool loop are unchanged.

Off unless Settings.anna_enabled (env ANNA_ENABLED) is true, so the web
API never routes traffic here.
"""

from __future__ import annotations

from typing import Any

from ..settings import Settings
from .base import DeploymentProvider


class AnnaProvider(DeploymentProvider):
    name = "anna"
    model_prefix = "anna/"
    api_key_setting = None
    # Never dialled: the custom handler talks to the host over stdio. A
    # value is required only because an empty base_url disables a provider.
    default_base_url = "https://anna.partners"
    # Billed by Anna in the user's compute units, not by us.
    PRICING: dict[str, tuple[float, float]] = {}

    def __init__(self, cfg: dict[str, Any], settings: Settings) -> None:
        super().__init__(cfg, settings)
        self.enabled = self.enabled and settings.anna_enabled

    def completion_params(
        self, model: str, reasoning: str | None = None
    ) -> dict[str, Any]:
        """Always state thinking explicitly.

        Anna counts reasoning tokens inside the output cap, so a thinking
        model left to its own default can spend the whole budget and return
        no text. ``anna_thinking`` is read by the Executa's custom handler:
        False = off, otherwise the effort level.
        """
        level = self.resolve_reasoning(reasoning)
        if level is None or level.lower() == "none":
            return {"anna_thinking": False}
        return {"anna_thinking": level.lower()}
