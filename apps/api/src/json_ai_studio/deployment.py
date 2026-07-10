"""Deployment Registry — multi-provider LLM backend selection.

Thin orchestrator over DeploymentProvider classes (providers/, ADR-0016).
deployments.yaml holds per-deployment tunables (enabled, models,
base_model); provider classes own endpoints, credentials (via pydantic
Settings), litellm prefixes, and pricing.

pick(model): round-robin per model across eligible deployments.
pick_default(): round-robin across enabled deployments — each serves its
own base_model; used when a request names no model (default traffic).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from .providers import PROVIDER_CLASSES, DeploymentProvider
from .settings import get_settings

_MODULE_DIR = os.path.dirname(__file__)
_logger = logging.getLogger("json_ai_studio.deployment")

# Reserved round-robin counter key for default (no explicit model) picks.
_DEFAULT_RR_KEY = "__default__"


class DeploymentRegistry:
    """Load, validate, and select backend deployments by model.

    Deployment order follows deployments.yaml. Skip disabled or
    model-mismatched deployments. Config loaded at module import time.
    """

    _deployments: dict[str, DeploymentProvider] = {}
    _model_to_deployments: dict[str, list[str]] = {}
    _rr_counters: dict[str, int] = {}

    @classmethod
    def load(cls) -> None:
        """Load YAML tunables, instantiate providers, build lookup tables."""
        yaml_path = os.path.join(_MODULE_DIR, "config", "deployments.yaml")
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        settings = get_settings()
        raw_deployments: dict[str, dict[str, Any]] = data.get("deployments", {})
        providers: list[DeploymentProvider] = []

        for name, cfg in raw_deployments.items():
            provider_cls = PROVIDER_CLASSES.get(name)
            if provider_cls is None:
                raise ValueError(
                    f"Unknown deployment provider: {name}. "
                    f"Known providers: {sorted(PROVIDER_CLASSES)}"
                )
            providers.append(provider_cls(cfg, settings))

        cls._build_lookup(providers)

    @classmethod
    def pick(cls, model: str) -> DeploymentProvider:
        """Return next eligible deployment for a model via round-robin."""
        names = cls._model_to_deployments.get(model, [])
        if not names:
            raise ValueError(f"No deployment supports model: {model}")

        counter = cls._rr_counters.get(model, 0)
        for i in range(len(names)):
            idx = (counter + i) % len(names)
            name = names[idx]
            if cls._deployments[name].enabled:
                cls._rr_counters[model] = (idx + 1) % len(names)
                return cls._deployments[name]

        raise RuntimeError(f"All deployments disabled for model: {model}")

    @classmethod
    def pick_default(cls) -> DeploymentProvider:
        """Round-robin enabled deployments; caller uses its base_model."""
        names = list(cls._deployments)
        if not names:
            raise RuntimeError("No deployments configured")

        counter = cls._rr_counters.get(_DEFAULT_RR_KEY, 0)
        for i in range(len(names)):
            idx = (counter + i) % len(names)
            name = names[idx]
            if cls._deployments[name].enabled:
                cls._rr_counters[_DEFAULT_RR_KEY] = (idx + 1) % len(names)
                return cls._deployments[name]

        raise RuntimeError("All deployments disabled: cannot pick a default")

    @classmethod
    def reload(cls) -> None:
        """Re-load YAML from disk."""
        cls._deployments = {}
        cls._model_to_deployments = {}
        cls._rr_counters = {}
        cls.load()

    @classmethod
    def list_deployments(cls) -> list[DeploymentProvider]:
        """Return all deployment providers in yaml order."""
        return list(cls._deployments.values())

    @classmethod
    def _build_lookup(cls, deployments: list[DeploymentProvider]) -> None:
        """Build model -> deployment name mapping."""
        lookup: dict[str, list[str]] = {}
        for cfg in deployments:
            for model in cfg.models:
                lookup.setdefault(model, []).append(cfg.name)
                # Also store prefixed version: "ollama/" + "gemma4:12b"
                lookup.setdefault(f"{cfg.model_prefix}{model}", []).append(cfg.name)
        cls._model_to_deployments = lookup
        cls._deployments = {cfg.name: cfg for cfg in deployments}


# Auto-load at module import time
try:
    DeploymentRegistry.load()
except Exception as e:
    print(f"WARNING: DeploymentRegistry failed to load: {e}")
