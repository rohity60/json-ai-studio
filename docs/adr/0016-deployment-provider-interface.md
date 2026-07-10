# 0016-deployment-provider-interface

**Date**: 2026-07-10
**Status**: Accepted

## Context

Backend selection logic was smeared across three places: `deployments.yaml` (base_url, api_key_env, model_prefix, models), `deployment.py` (env resolution, validation, round-robin), and `gateway.py` (`MODEL_PRICING` dict, model prefixing, a hardcoded `"ollama/gemma4:12b"` default). Adding a backend meant touching all three, and the hardcoded default pinned all no-model traffic (chat + explain — the only real entry points) to Ollama regardless of which deployments were enabled. With the repo being open-sourced, adding a provider must be a one-file contribution, and the default model must come from config.

## Decision

**Provider interface** (`providers/base.py`): each LLM backend is a `DeploymentProvider` subclass, one file per provider (`google_ai_studio.py`, `nvidia_nim.py`, `openrouter.py`, `ollama.py`). The class owns:

- `name` (registry key = yaml entry name), `model_prefix` (litellm prefix), `default_base_url`
- `api_key_setting` — the **pydantic Settings field** holding the credential (ADR-0015 config seam; providers never read `os.environ`). Missing/empty key auto-disables the deployment at load with a warning.
- `PRICING` — per-model `(prompt, completion)` USD per 1K tokens. `pricing(model)` strips the prefix, unknown models cost `(0.0, 0.0)`. Gemma on Google AI Studio is free tier: `gemma-4-26b-a4b-it: (0.0, 0.0)`.
- Overridable seams: `_resolve_base_url()` (Ollama returns `settings.ollama_base_url` from env `OLLAMA_BASE_URL` — no hardcoded default; unset disables the deployment), `_resolve_api_key()`, `litellm_model()`.

**deployments.yaml slims to tunables**: `enabled`, `models`, `base_model`, `reasoning` per deployment. Endpoints/credentials/prefixes/pricing are code (provider class), toggles and model lists are config.

**Generic reasoning knob**: yaml `reasoning: none|minimal|low|medium|high` is provider-agnostic; `completion_params(model)` translates it into backend kwargs — OpenAI-style `reasoning_effort` by default, `generationConfig.thinkingConfig.thinkingLevel` for Google (Gemma 4 rejects `reasoning_effort` outright and 500s without a thinkingConfig; litellm passes the `thinkingConfig` kwarg through). Omitting the yaml key sends no reasoning params.

**Config-driven default model**: `DeploymentRegistry.pick_default()` round-robins enabled deployments in yaml order (reserved `__default__` counter); the chosen deployment serves its own `base_model` (google/nvidia/openrouter → `gemma-4-26b-a4b-it`, ollama → `gemma4:12b`). `GatewayService._resolve_model()` now returns `None` when no explicit model/profile matches, triggering this path. Explicit models still route via `pick(model)` (per-model round-robin, unchanged).

**Gateway pricing** delegates to `deployment.pricing(model)`; the old `MODEL_PRICING` dict remains only as a fallback for models no deployment serves (`gpt-4.1`, Claude rows). Usage records now log `provider: deployment.name` instead of a hardcoded `"ollama"`.

Adding a backend = provider subclass file + entry in `providers/__init__.py:PROVIDER_CLASSES` + yaml entry (+ Settings field for its key).

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Keep everything in yaml with `${ENV}` placeholders | Rejected in review: duplicates the pydantic Settings seam with ad-hoc env parsing; no home for per-provider behavior (pricing, URL logic). |
| litellm Router (built-in deployments/fallbacks) | Heavier abstraction than needed; hides the credit/pricing hooks the gateway needs per call. |
| Priority-order default (first enabled wins) | Considered, then reverted to round-robin: base models serve anonymous traffic, spreading it across enabled backends is preferred. |
| Entry-points/plugin discovery for providers | Overkill for an MVP; a dict in `providers/__init__.py` is greppable and explicit. |

## Consequences

- Contributors add providers without touching gateway or registry logic.
- Default traffic alternates across enabled deployments per request; a flapping backend (e.g. tunnel down but deployment enabled) still receives its share — no health-based failover yet.
- Free-tier pricing (0.0) means google-served default traffic deducts no credits from the anonymous pool (accepted).
- `AI_PROFILES` still maps to fixed models (`premium` → `gpt-4.1` has no serving deployment and errors if requested; pre-existing, out of scope).
