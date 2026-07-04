# Backend Requirements — JSON AI Studio Deployment Support

Derived from PRD v1.0 + cost-credits feature. Only what the **server / API layer** must implement.
Technical decisions documented in `docs/adr/`.

---

## 1. Deployment Configuration Service

| # | Requirement | Priority |
|---|-------------|----------|
| D-01 | `apps/api/config/deployments.yaml` — YAML file defining LLM backend deployments. Each deployment has: `enabled`, `base_url`, `api_key_env`, `model_prefix`, `models` | MVP |
| D-02 | Environment variable placeholders `${ENV_VAR_NAME}` in YAML resolved at startup from `os.environ`. Fail if missing | MVP |
| D-03 | `DeploymentRegistry` class — in-memory singleton. Loads YAML, builds model→deployment lookup, provides round-robin selection | MVP |
| D-04 | Round-robin per model: each `pick(model)` call advances a counter, cycles through eligible deployments. Skips disabled or model-mismatched entries | MVP |
| D-05 | Three cloud providers configured: Google AI Studio (`generativelanguage.googleapis.com`), NVIDIA NIM API (`integrate.api.nvidia.com`), OpenRouter (`openrouter.ai/api/v1`) | MVP |
| D-06 | Local Ollama deployment remains: `http://localhost:11434/v1`, no API key required | MVP |
| D-07 | `model_prefix` prepended to resolved model string for litellm. E.g. `google/` + `gemma-4-26b-a4b-it` = `google/gemma-4-26b-a4b-it` | MVP |

## 2. Gateway Integration

| # | Requirement | Priority |
|---|-------------|----------|
| G-01 | `GatewayService.invoke()` calls `DeploymentRegistry.pick(model)` before each `litellm.acompletion()` call | MVP |
| G-02 | `litellm.acompletion()` receives `model`, `base_url`, `api_key` from selected deployment config | MVP |
| G-03 | SSE `event: deployment` emitted after `event: thinking` starts, before first content chunk. Payload: `{model, deployment, provider}` | MVP |
| G-04 | If model not found in any deployment: `event: error` with "No deployment supports model: X". No LLM call | MVP |
| G-05 | If all deployments disabled for model: `event: error` with "All deployments disabled". No LLM call | MVP |
| G-06 | Round-robin counter is per-model. Different models have independent counters | MVP |

## 3. Data Model

### DeploymentConfig

```python
from dataclasses import dataclass

@dataclass
class DeploymentConfig:
    name: str                # e.g. "google_ai_studio"
    enabled: bool            # toggle on/off
    base_url: str            # litellm base_url
    api_key_env: str         # env var name (empty = no key)
    model_prefix: str        # prefix for model string
    models: list[str]        # models this deployment serves
```

### Module-Level State in `deployment.py`

```python
_deployments: dict[str, DeploymentConfig] = {}     # name → config
_model_to_deployments: dict[str, list[str]] = {}    # model → [deployment_names]
_rr_counters: dict[str, int] = {}                   # model → current index
```

### R7 — Deployment Registry Load

- `DeploymentRegistry.load(yaml_path)` reads YAML, resolves `${VAR}` from `os.environ`, builds `_model_to_deployments` lookup.
- Fails fast if `api_key_env` references missing env var.
- Fails fast if YAML is malformed.
- Called once at module import time or on explicit `reload()`.

### R8 — Deployment Pick

- `DeploymentRegistry.pick(model)` returns next eligible `DeploymentConfig` via round-robin.
- Skips disabled deployments. Skips deployments whose `models` list doesn't contain the model.
- Counter increments modulo len(eligible_deployments).
- Raises `ValueError` if model not in any deployment.
- Raises `RuntimeError` if all eligible deployments are disabled.

### R9 — Env Var Resolution

- `_resolve_env(value)` replaces `${VAR_NAME}` with `os.environ.get(VAR_NAME)`.
- Fails with `ValueError` if env var not set.
- Static method. No state mutation.

## 4. Data Flow

### 4.1 Happy Path

```
1. ChatRequest arrives: model="gemma-4-26b-a4b-it", profile=None
2. _resolve_model(None, None) → "gemma-4-26b-a4b-it"
3. DeploymentRegistry.pick("gemma-4-26b-a4b-it")
    → _model_to_deployments["gemma-4-26b-a4b-it"] = ["google_ai_studio", "nvidia_nim", "openrouter"]
    → counter = 0 → picks "google_ai_studio"
    → counter increments to 1
4. litellm.acompletion(model="google/gemma-4-26b-a4b-it", base_url="...", api_key="...")
5. Stream chunks → SSE thinking events
6. Next request: same model → picks "nvidia_nim" (counter = 1)
7. Next request: same model → picks "openrouter" (counter = 2)
8. Next request: same model → picks "google_ai_studio" (counter wraps to 0)
```

### 4.2 Disabled Deployment

```
1. Same model, round-robin lands on "nvidia_nim"
2. nvidia_nim.enabled = false → skip
3. Try next: "openrouter" → enabled = true → return
4. Counter updated to skip over disabled entries
```

### 4.3 Model Not Supported

```
1. Model "unknown-model" not in any deployment's models list
2. DeploymentRegistry.pick() raises ValueError
3. GatewayService catches → yields event:error with "No deployment supports model: unknown-model"
4. No LLM call made
```

## 5. YAML Config Schema

```yaml
deployments:
   <deployment_name>:
    enabled: bool                  # Required. true/false toggle.
    base_url: string               # Required. litellm base_url.
    api_key_env: string            # Required. Env var name. Empty = no key.
    model_prefix: string           # Required. Prefix for model string.
    models:                        # Required. List of model strings.
       - string
```

**Validation rules:**
- `enabled` must be a boolean.
- `base_url` must start with `http://` or `https://`.
- `model_prefix` must end with `/`.
- `models` must be non-empty list of strings.
- `api_key_env` must be a string. Empty = no key required.
- Deployment names must be unique.

## 6. API Summary (Routes)

No new endpoints added. Deployment selection is internal to `GatewayService.invoke()`.

| Component | Purpose |
|-----------|---------|
| `DeploymentRegistry.load(yaml_path)` | Load config from YAML (called at startup) |
| `DeploymentRegistry.pick(model)` | Select next deployment via round-robin |
| `DeploymentRegistry.reload()` | Re-load YAML from disk |
| `DeploymentRegistry.list_deployments()` | Return all configs (debug/admin) |

## 7. Excluded from MVP

- Health check endpoint — ping each deployment for liveness
- Weighted round-robin — bias toward cheaper/faster providers
- Latency-aware selection — track response times, prefer faster
- Circuit breaker — auto-disable failed deployments after N failures
- Per-request model override — force a specific deployment via header
- Config hot-reload — watch YAML file for changes, auto-reload
- Usage dashboard — cost per deployment, tokens per provider
- Fallback chain — primary → secondary → tertiary per model
- Multi-model deployments — single deployment serving multiple model families
- DB persistence — swap in-memory registry for disk/DB

---

*End of requirements. Feature branch: `deployments-support`. Implementation files: `deployment.py`, `gateway.py`, `config/deployments.yaml`.*
