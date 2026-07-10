"""Deployment provider interface (ADR-0016).

Each LLM backend is a DeploymentProvider subclass, one file per provider
in this package. The class owns the endpoint, credential seam, litellm
model prefix, pricing, and translation of generic tunables (reasoning)
into backend-specific params. deployments.yaml holds per-deployment
tunables (enabled, models, base_model, reasoning); secrets and endpoint
overrides resolve through pydantic Settings (settings.py) — never raw
os.environ.
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any, ClassVar

from ..settings import Settings

_logger = logging.getLogger("json_ai_studio.providers")


class DeploymentProvider(ABC):
    """One LLM backend. Subclasses set the class-level contract below.

    To add a provider: subclass this in a new file, register the class in
    providers/__init__.py PROVIDER_CLASSES, and add a matching entry to
    config/deployments.yaml.
    """

    # --- subclass contract -------------------------------------------------
    # Registry key; must match the deployments.yaml entry name.
    name: ClassVar[str]
    # litellm provider prefix, must end with "/" (e.g. "gemini/").
    model_prefix: ClassVar[str]
    # Settings field holding the API key (e.g. "google_ai_studio_api_key").
    # None = keyless backend. A required-but-missing key disables the
    # deployment at load time (warning, not an error).
    api_key_setting: ClassVar[str | None] = None
    # Fixed endpoint. Subclasses with env-driven endpoints override
    # _resolve_base_url() instead.
    default_base_url: ClassVar[str] = ""
    # model -> (prompt, completion) USD per 1K tokens. Unprefixed model
    # names. Unknown models cost (0.0, 0.0).
    PRICING: ClassVar[dict[str, tuple[float, float]]] = {}

    def __init__(self, cfg: dict[str, Any], settings: Settings) -> None:
        """Resolve instance state from a deployments.yaml entry + Settings."""
        if not self.model_prefix.endswith("/"):
            raise ValueError(f"model_prefix for {self.name} must end with /")

        self.models: list[str] = list(cfg.get("models") or [])
        if not self.models:
            raise ValueError(f"models list for {self.name} must not be empty")

        self.base_model: str = str(cfg.get("base_model", ""))
        if self.base_model not in self.models:
            raise ValueError(
                f"base_model for {self.name} must be one of its models "
                f"{self.models}, got: {self.base_model!r}"
            )

        # Generic reasoning level from yaml ("none", "minimal", "low", ...).
        # None = deployment says nothing about reasoning; no params sent.
        # completion_params() translates it into backend-specific kwargs.
        raw_reasoning = cfg.get("reasoning")
        self.reasoning: str | None = (
            str(raw_reasoning) if raw_reasoning is not None else None
        )

        # Empty base_url = endpoint env var not set -> deployment disabled
        # (warning, not an error). Non-empty must be a valid http(s) URL.
        self.base_url: str = self._resolve_base_url(cfg, settings) or ""
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid base_url for {self.name}: must start with "
                "http:// or https://"
            )

        self.api_key: str = self._resolve_api_key(settings)
        self.enabled: bool = bool(cfg.get("enabled", False))
        if not self.base_url:
            _logger.warning(
                "Missing base_url for deployment %s (disabled); "
                "set its endpoint env var",
                self.name,
            )
            self.enabled = False
        if self.api_key_setting and not self.api_key:
            _logger.warning(
                "Missing setting: %s (deployment %s disabled)",
                self.api_key_setting,
                self.name,
            )
            self.enabled = False

    # --- overridable resolution seams ---------------------------------------

    def _resolve_base_url(self, cfg: dict[str, Any], settings: Settings) -> str:
        """Endpoint URL. Default: the class constant."""
        return self.default_base_url

    def _resolve_api_key(self, settings: Settings) -> str:
        """Credential from Settings. Empty string when keyless or unset."""
        if not self.api_key_setting:
            return ""
        return getattr(settings, self.api_key_setting, None) or ""

    def completion_params(self, model: str) -> dict[str, Any]:
        """Extra litellm kwargs for a completion on this backend.

        Translates the generic `reasoning` level from deployments.yaml
        into backend params. Default: OpenAI-style reasoning_effort.
        Override for backends with different controls (e.g. Google's
        generationConfig.thinkingConfig).
        """
        if self.reasoning is None:
            return {}
        return {"reasoning_effort": self.reasoning}

    # --- shared behavior -----------------------------------------------------

    def litellm_model(self, model: str) -> str:
        """Fully-prefixed model id for litellm."""
        if model.startswith(self.model_prefix):
            return model
        return f"{self.model_prefix}{model}"

    def pricing(self, model: str) -> tuple[float, float]:
        """(prompt, completion) USD per 1K tokens; (0.0, 0.0) if unknown."""
        if model.startswith(self.model_prefix):
            model = model[len(self.model_prefix) :]
        return self.PRICING.get(model, (0.0, 0.0))
