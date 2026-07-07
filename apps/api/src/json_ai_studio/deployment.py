"""Deployment Registry — multi-provider LLM backend selection.

Loads YAML config with ${ENV_VAR} placeholders. Resolves env vars at startup.
Round-robin per model across eligible deployments. Skip disabled / model-mismatched.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")
_MODULE_DIR = os.path.dirname(__file__)
_logger = logging.getLogger("json_ai_studio.deployment")


@dataclass
class DeploymentConfig:
    """Single deployment configuration."""

    name: str
    enabled: bool
    base_url: str
    api_key: str
    model_prefix: str
    models: list[str]


class DeploymentRegistry:
    """Load, validate, and select backend deployments by model.

    Round-robin per model. Skip disabled or model-mismatched deployments.
    Config loaded from YAML at module import time.
    """

    _deployments: dict[str, DeploymentConfig] = {}
    _model_to_deployments: dict[str, list[str]] = {}
    _rr_counters: dict[str, int] = {}

    @classmethod
    def load(cls) -> None:
        """Load YAML, resolve env vars, build lookup tables."""
        yaml_path = os.path.join(_MODULE_DIR, "config", "deployments.yaml")
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        raw_deployments: dict[str, dict[str, Any]] = data.get("deployments", {})
        configs: list[DeploymentConfig] = []

        for name, cfg in raw_deployments.items():
            base_url = str(cfg["base_url"])
            if not base_url.startswith(("http://", "https://")):
                raise ValueError(
                    f"Invalid base_url for {name}: must start with http:// or https://"
                )

            api_key_env = str(cfg.get("api_key_env", ""))
            if api_key_env and api_key_env not in os.environ:
                _logger.warning(
                    "Missing env var: %s (deployment %s disabled)",
                    api_key_env,
                    name,
                )
                enabled = False
            else:
                enabled = bool(cfg.get("enabled", False))
            api_key = os.environ.get(api_key_env, "") if api_key_env else ""

            model_prefix = str(cfg["model_prefix"])
            if not model_prefix.endswith("/"):
                raise ValueError(f"model_prefix for {name} must end with /")

            models = list(cfg["models"])
            if not models:
                raise ValueError(f"models list for {name} must not be empty")

            configs.append(
                DeploymentConfig(
                    name=name,
                    enabled=enabled,
                    base_url=base_url,
                    api_key=api_key,
                    model_prefix=model_prefix,
                    models=models,
                )
            )

        cls._build_lookup(configs)

    @classmethod
    def pick(cls, model: str) -> DeploymentConfig:
        """Return next eligible deployment via round-robin."""
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
    def reload(cls) -> None:
        """Re-load YAML from disk."""
        cls._deployments = {}
        cls._model_to_deployments = {}
        cls._rr_counters = {}
        cls.load()

    @classmethod
    def list_deployments(cls) -> list[DeploymentConfig]:
        """Return all deployment configs."""
        return list(cls._deployments.values())

    @staticmethod
    def _resolve_env(value: str) -> str:
        """Replace ${VAR_NAME} with os.environ[VAR_NAME]."""

        def _replacer(match: re.Match) -> str:
            var = match.group(1)
            env_val = os.environ.get(var)
            if env_val is None:
                raise ValueError(
                    f"Missing env var: {var} (required by deployment config)"
                )
            return env_val

        return _ENV_PATTERN.sub(_replacer, value)

    @classmethod
    def _build_lookup(cls, deployments: list[DeploymentConfig]) -> None:
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
