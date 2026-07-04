# Deployment Support — Task List

**Feature branch:** `deployments-support`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Create `apps/api/config/deployments.yaml` — YAML config with 3 cloud providers (Google AI Studio, NVIDIA NIM, OpenRouter) + local Ollama. Env var placeholders. | done |
| 2 | Create `apps/api/src/json_ai_studio/deployment.py` — `DeploymentConfig` dataclass, `_ENV_PATTERN`, `_resolve_env()` static method | done |
| 3 | Implement `DeploymentRegistry.load()` — read YAML, validate fields, resolve env vars, build `_model_to_deployments` lookup | done |
| 4 | Implement `DeploymentRegistry.pick()` — round-robin per model, skip disabled/mismatched, raise errors | done |
| 5 | Implement `DeploymentRegistry.reload()` + `list_deployments()` + `_build_lookup()` — helper methods | done |
| 6 | Modify `gateway.py` — import `DeploymentRegistry`, call `pick()` before `litellm.acompletion()`, add `event: deployment` SSE event, pass `base_url`/`api_key` | done |
| 7 | Verify — run app, test round-robin cycles, disabled deployment skip, model-not-found error, local Ollama still works | done |

---

*Total: 7 tasks. Sequential: 1→2→3→4→5→6→7.*
