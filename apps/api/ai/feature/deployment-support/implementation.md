# JSON AI Studio — Deployment Support Implementation Guide

**Feature branch:** `deployments-support`
**Requirements:** `requirements.md`

---

## 1. Architecture

```
ChatRequest (model? / profile?)
     → GatewayService._resolve_model(model, profile)
     → model string (e.g. "gemma-4-26b-a4b-it")
     → DeploymentRegistry.pick(model)
     → DeploymentConfig (base_url, api_key_env, model_prefix)
     → litellm.acompletion(model="<model_prefix><model>", ... base_url=..., api_key=...)
```

**Key principle:** `DeploymentRegistry` is a singleton class with module-level state. `GatewayService.invoke()` calls `DeploymentRegistry.pick(model)` before each `litellm.acompletion()` call. The registry returns a `DeploymentConfig` with `base_url`, `api_key` (resolved from env), and `model_prefix` (for litellm model string construction).

---

## 2. Component Details

### 2.1 `deployments.yaml` — Configuration File

Location: `apps/api/config/deployments.yaml`

```yaml
# Deployment registry — multi-provider LLM backend configuration.
# Environment variable placeholders: ${ENV_VAR_NAME}
# Resolved at startup from os.environ. Fails if missing.

deployments:
    # Google AI Studio — Gemini family
  google_ai_studio:
    enabled: true
    base_url: "https://generativelanguage.googleapis.com/v1beta"
    api_key_env: "GOOGLE_AI_STUDIO_API_KEY"
    model_prefix: "google/"
    models:
        - "gemma-4-26b-a4b-it"

    # NVIDIA NIM API — GPU-accelerated inference
  nvidia_nim:
    enabled: true
    base_url: "https://integrate.api.nvidia.com/v1"
    api_key_env: "NVIDIA_NIM_API_KEY"
    model_prefix: "nvidia/"
    models:
        - "gemma-4-26b-a4b-it"

    # OpenRouter — aggregated multi-provider API
  openrouter:
    enabled: true
    base_url: "https://openrouter.ai/api/v1"
    api_key_env: "OPENROUTER_API_KEY"
    model_prefix: "openrouter/"
    models:
        - "gemma-4-26b-a4b-it"

    # Local Ollama — development / offline
  ollama_local:
    enabled: true
    base_url: "http://localhost:11434/v1"
    api_key_env: ""
    model_prefix: "ollama/"
    models:
        - "qwen3.6:35b-mlx"
        - "gemma4:12b"
```

### 2.2 `deployment.py` — Full Module

Location: `apps/api/src/json_ai_studio/deployment.py`

```python
"""Deployment Registry — multi-provider LLM backend selection.

Loads YAML config with ${ENV_VAR} placeholders. Resolves env vars at startup.
Round-robin per model across eligible deployments. Skip disabled / model-mismatched.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


@dataclass
class DeploymentConfig:
    """Single deployment configuration."""
    name: str
    enabled: bool
    base_url: str
    api_key_env: str
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
    def load(cls, yaml_path: str) -> None:
        """Load YAML, resolve env vars, build lookup tables."""
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        raw_deployments: dict[str, dict[str, Any]] = data.get("deployments", {})
        configs: list[DeploymentConfig] = []

        for name, cfg in raw_deployments.items():
            base_url = str(cfg["base_url"])
            if not base_url.startswith(("http://", "https://")):
                raise ValueError(f"Invalid base_url for {name}: must start with http:// or https://")

            api_key_env = str(cfg.get("api_key_env", ""))
            if api_key_env and api_key_env not in os.environ:
                raise ValueError(f"Missing env var: {api_key_env} (required by deployment {name})")

            model_prefix = str(cfg["model_prefix"])
            if not model_prefix.endswith("/"):
                raise ValueError(f"model_prefix for {name} must end with /")

            models = list(cfg["models"])
            if not models:
                raise ValueError(f"models list for {name} must not be empty")

            configs.append(DeploymentConfig(
                name=name,
                enabled=bool(cfg.get("enabled", False)),
                base_url=base_url,
                api_key_env=api_key_env,
                model_prefix=model_prefix,
                models=models,
            ))

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
        cls.load("config/deployments.yaml")

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
                raise ValueError(f"Missing env var: {var} (required by deployment config)")
            return env_val
        return _ENV_PATTERN.sub(_replacer, value)

    @classmethod
    def _build_lookup(cls, deployments: list[DeploymentConfig]) -> None:
        """Build model → deployment name mapping."""
        lookup: dict[str, list[str]] = {}
        for cfg in deployments:
            for model in cfg.models:
                lookup.setdefault(model, []).append(cfg.name)
        cls._model_to_deployments = lookup
        cls._deployments = {cfg.name: cfg for cfg in deployments}
```

### 2.3 `gateway.py` — Changes to `invoke()`

**Current code (lines to replace):**

```python
# Around line 281-303 in gateway.py

resolved_model = GatewayService._resolve_model(model, profile)
# ... credit checks ...

response = await litellm.acompletion(
    model=resolved_model,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ],
    stream=True,
    timeout=120.0,
    stream_options={"include_usage": True},
)
```

**Becomes:**

```python
from .deployment import DeploymentConfig, DeploymentRegistry

resolved_model = GatewayService._resolve_model(model, profile)
# ... credit checks ...

# Select deployment for this model
deployment: DeploymentConfig = DeploymentRegistry.pick(resolved_model)
litellm_model: str = f"{deployment.model_prefix}{resolved_model}"

# Emit deployment selection event
yield f'event: deployment\ndata{json.dumps({
    "model": resolved_model,
    "deployment": deployment.name,
    "provider": deployment.model_prefix,
})}\n\n'

response = await litellm.acompletion(
    model=litellm_model,
    base_url=deployment.base_url,
    api_key=deployment.api_key or None,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ],
    stream=True,
    timeout=120.0,
    stream_options={"include_usage": True},
)
```

---

## 3. Data Flow

### 3.1 Successful Request

```
1. ChatRequest arrives: model="gemma-4-26b-a4b-it", profile=None
2. _resolve_model(None, None) → "gemma-4-26b-a4b-it"
3. DeploymentRegistry.pick("gemma-4-26b-a4b-it")
     → _model_to_deployments["gemma-4-26b-a4b-it"] = ["google_ai_studio", "nvidia_nim", "openrouter"]
     → counter for model = 0 → picks "google_ai_studio"
     → counter increments to 1
4. litellm.acompletion(model="google/gemma-4-26b-a4b-it", base_url="...", api_key="...")
5. Stream chunks → SSE thinking events
6. Next request: same model → picks "nvidia_nim" (counter = 1)
7. Next request: same model → picks "openrouter" (counter = 2)
8. Next request: same model → picks "google_ai_studio" (counter wraps to 0)
```

### 3.2 Disabled Deployment

```
1. Same model, round-robin lands on "nvidia_nim"
2. nvidia_nim.enabled = false → skip
3. Try next: "openrouter" → enabled = true → return
4. Counter updated to skip over disabled entries
```

### 3.3 Model Not Supported

```
1. Model "unknown-model" not in any deployment's models list
2. DeploymentRegistry.pick() raises ValueError
3. GatewayService catches → yields event:error with "No deployment supports model: unknown-model"
4. No LLM call made
```

---

## 4. Error Handling

| Error | When | Response |
|-------|------|----------|
| `ValueError` | Model not in any deployment's models list | `event: error` with "No deployment supports model: X" |
| `RuntimeError` | All deployments disabled for model | `event: error` with "All deployments disabled" |
| `ValueError` | Missing env var in YAML | Server startup fails with traceback |
| `yaml.YAMLError` | Malformed YAML | Server startup fails with traceback |

---

## 5. Assumptions & Constraints

1. **In-memory only.** No database. Registry state lost on restart. Matches ADR-0006.
2. **Single-threaded.** FastAPI dev server, single worker. No locking needed.
3. **YAML dependency.** Requires `PyYAML`. Add to `requirements.txt` if not present.
4. **Env var resolution at startup.** Not per-request. Config is loaded once, cached.
5. **Round-robin is per-model.** Different models have independent counters.
6. **Model prefix is mandatory.** Every deployment must specify `model_prefix`. No bare model strings.
7. **Disabled deployments still listed.** `pick()` skips them but they remain in `list_deployments()`.
8. **No hot-reload of env vars.** Restart server to pick up new env values. YAML reload re-reads file.
9. **Local Ollama stays.** `ollama_local` deployment with `http://localhost:11434/v1` remains as a deployment entry.
10. **No failover mid-stream.** If a deployment fails during streaming, the error propagates. Failover is at request level only.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/api/src/json_ai_studio/deployment.py` | **NEW** | `DeploymentRegistry`, `DeploymentConfig`, YAML loader, env resolver |
| `apps/api/src/json_ai_studio/gateway.py` | **MODIFIED** | `invoke()` uses `DeploymentRegistry.pick()`, adds `event: deployment` |
| `apps/api/config/deployments.yaml` | **NEW** | Deployment config with env var placeholders |
| `apps/api/ai/feature/deployment-support/implementation.md` | **NEW** | This document |

**No changes to:** `models.py`, `store.py`, `auth.py`, `utils.py`, `main.py`.

---

## 7. Verification

### Manual Tests

1. **Happy path — round-robin:** Send 3+ chat messages with same model. Verify SSE `event: deployment` cycles through all 3 cloud providers (Google, NVIDIA, OpenRouter).
2. **Disabled deployment:** Set `nvidia_nim.enabled: false` in YAML. Restart. Send chat. Verify NVIDIA never appears in `event: deployment`.
3. **Model not supported:** Send model `unknown-model`. Verify `event: error` with "No deployment supports model: unknown-model".
4. **Local Ollama still works:** Send message with `gemma4:12b` model. Verify `ollama_local` deployment selected, Ollama responds.
5. **Missing env var:** Remove `GOOGLE_AI_STUDIO_API_KEY` from env. Set `google_ai_studio.enabled: true`. Restart server. Verify startup fails with "Missing env var: GOOGLE_AI_STUDIO_API_KEY".
6. **YAML reload:** Call `DeploymentRegistry.reload()` (or test endpoint). Verify config re-read from disk.
7. **Cross-model round-robin independence:** Send requests with `gemma-4-26b-a4b-it` and `gemma4:12b` interleaved. Verify each model's counter advances independently.

### Code Review Checklist

- [ ] `DeploymentRegistry.load()` reads YAML, resolves `${VAR}` from `os.environ`, builds lookup tables.
- [ ] `DeploymentRegistry.pick()` implements round-robin per model, skips disabled.
- [ ] `_resolve_env()` fails fast on missing env var.
- [ ] `gateway.py invoke()` calls `DeploymentRegistry.pick()`, constructs litellm model string with prefix.
- [ ] `event: deployment` SSE event emitted before first content chunk.
- [ ] Error handling: model not found → `event: error`, all disabled → `event: error`.
- [ ] No external dependencies beyond `yaml` (PyYAML).
- [ ] Module docstring follows existing style.
- [ ] All methods are `@classmethod` on singleton class.
- [ ] YAML schema validated at load time.

---

## 8. Glossary

| Term | Definition |
|------|-----------|
| **Deployment** | A backend LLM endpoint configuration. Has `base_url`, `api_key_env`, `model_prefix`, `models`. |
| **DeploymentConfig** | Dataclass holding a single deployment's settings. |
| **DeploymentRegistry** | Singleton class. Loads YAML, resolves env vars, provides round-robin selection. |
| **Round-Robin** | Circular distribution across deployments for a given model. Each `pick()` advances counter. |
| **Model Prefix** | String appended before model name for litellm. E.g., `google/` + `gemma-4-26b-a4b-it` = `google/gemma-4-26b-a4b-it`. |
| **Env Var Placeholder** | `${VAR_NAME}` in YAML. Resolved from `os.environ` at startup. |
| **Enabled** | Boolean toggle. `false` → deployment skipped by round-robin. |
| **Base URL** | litellm `base_url` parameter. Endpoint address for the deployment. |
| **API Key Env** | Env var name containing the API key for the deployment. Empty string = no key needed. |

---

*End of implementation guide. Feature branch: `deployments-support`.*
