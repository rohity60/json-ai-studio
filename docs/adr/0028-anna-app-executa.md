# 0028-anna-app-executa

**Date**: 2026-11-12
**Status**: Accepted

## Context

JSON AI Studio ships as an **Anna App** (anna.partners, slug `json-ai-studio`) to join Anna's Founding Builder program: monthly grants by Qualified App MAU and a 70% share of usage profit on Anna paid credits. Two platform facts shape the design:

- **Anna counts what it can see.** A Qualified App Run is measured from Anna's server-side records, and the revenue share applies to usage billed through Anna's own credits. LLM calls made with our provider keys are invisible to both.
- **An Anna App is not a hosted web app.** It is a static bundle rendered in a sandboxed iframe plus optional **Executas**: stdio JSON-RPC processes that Anna spawns on the user's machine or a Cloud Agent microVM. An Executa reaches the LLM and per-user storage only by reverse RPC to the Anna host (`sampling/createMessage`, `storage/*`, `files/*`).

Options considered:

1. **Bundle calls our FastAPI backend** (`external_origins`), our LiteLLM keys. Fastest, but runs are invisible to Anna, we pay for inference, and the app depends on our hosting.
2. **Bundle calls our backend for prompt building / diff application, the LLM call goes through Anna from the iframe.** Counts for Anna, still depends on our hosting.
3. **Executa hosts the engine; nothing calls our backend.** More packaging work; fully inside Anna.

Within option 3, two ways to reuse the engine: new interfaces (`LlmGateway`, `TokenBudget`) with Anna implementations, or treating Anna as one more LLM provider.

## Decision

1. **Option 3: the engine runs in an Executa** (`apps/anna/executas/json-ai-studio/`). The Anna App never calls the FastAPI backend.

2. **Anna is a `DeploymentProvider`** (`providers/anna.py`, ADR-0016), `model_prefix = "anna/"`, enabled only when `ANNA_ENABLED` is true. The Executa registers a litellm **custom provider** under `anna/` that turns each `litellm.acompletion` into `sampling/createMessage`. The gateway, turn planner, history replay, bulk edits and edit-safety guard are unchanged and shared with the web API. `completion_params` always states thinking explicitly (`anna_thinking`), because Anna counts reasoning tokens inside the output cap.

3. **One LLM call per turn on Anna.** The host caps a tool invoke at 8 sampling calls, 32,000 tokens in total and 8,192 output tokens per call. The `anna` deployment therefore sets `supports_tools: false` and `tpm_input_limit: 24000` (× 0.8 headroom): the planner picks inline or skeleton for a single call, else `input_too_large` with `focus_path` (ADR-0025). The Executa resets the deployment budget window at the start of each turn, since the cap is per invoke, not per minute. Our own credit and rate limits are lifted there; Anna's compute-unit quota is the gate.

4. **Sessions live in Anna Persistent Storage** behind the existing `SessionStore` (ADR-0013). `set_store()` swaps the backend behind the module-level `store`; services are untouched. `ApsSessionStore` keeps a session in KV up to 48 KB and in object storage above that (presigned PUT/GET), scope `app`.

5. **The UI reuses the web app's React code unmodified** (`apps/anna/ui`, Vite). The build resolves every import of `apps/web/src/lib/api` to an adapter with the same functions over Executa tools, so `SessionContext.tsx` and the components run as-is. Chat turns run as async tool jobs; their progress events are the same events the web SSE stream carries.

6. **The Executa ships as a PyInstaller `--onedir` binary** per platform (`build_binary.sh`, CI workflow `anna-executa.yml`), built from the Executa's `uv.lock`, with `litellm` pinned to the API's version. No Anna SDK dependency: the reverse-RPC client is ~130 lines of our own (`jstudio/rpc.py`).

## Consequences

- **Good:** runs and LLM usage are visible to Anna; no inference cost and no hosting dependency for the Anna App; one engine for both products, so prompt and diff changes ship to both.
- **Good:** the web API is unaffected — `anna` is disabled without `ANNA_ENABLED`, and the in-memory store stays the default.
- **Bad:** no lookup-tool loop on Anna (ADR-0024). Documents too large for one ~19k-token call lean on the skeleton prompt and bulk ops, or the user must pick a section.
- **Bad:** answer quality depends on the model each Anna user has selected; we do not choose it.
- **Bad:** the binary carries litellm, FastAPI and SQLAlchemy on its import path (~51 MB archive, ~96 MB unpacked on darwin-arm64). The alternative — interfaces with a litellm-free Anna implementation — was rejected to avoid forking orchestration; it remains the fallback if size or cold start becomes a problem.
- **Bad:** each session save is several storage round trips (~1–3 s on real APS). Acceptable for v1; batch later.
- Desktop only: Executas do not run on Anna mobile.
- stdout of the plugin is reserved for protocol frames; `sys.stdout` is repointed to stderr at startup because LiteLLM logs to stdout.

## References

- ADR-0013 (session store seam), ADR-0016 (deployment providers), ADR-0021 (chat history), ADR-0024 (lookup tools), ADR-0025 (token budget and turn planner)
- `apps/anna/README.md`; plan and file list: `apps/web/ai/feature/anna-app/`
- Anna developer docs corpus: `https://anna.partners/llms-full.txt` (fetch with `apps/web/ai/feature/anna-app/fetch-anna-docs.sh`)
