# Anna App migration — file-by-file list (2026-11-11)

Companion to `plan.md` (rev 3). Nothing here is written yet. Rev 3: stage A = Anna as LLM provider; gateway unchanged.
Scaffold reference: `anna-app init json-ai-studio --slug json-ai-studio` (CLI 0.1.64) produces
`manifest.json` (schema 4), `app.json`, `bundle/{index.html,app.js}`,
`executas/json-ai-studio/{json_ai_studio_plugin.py,pyproject.toml}`.
`required_executas[].tool_id` is the dev id `tool-dev-json-ai-studio`; real id minted at
anna.partners/executa → My Tools → Mint before first release.

## A. Shared Python core — Anna as an LLM provider (rev 3, 2026-11-12)

Decision: Anna is one more `DeploymentProvider` (ADR-0016). Gateway, turn planner, tool loop,
progress events, history replay, bulk edits, edit guard stay **unchanged**. Only transport differs:
litellm custom provider `anna/` → Anna sampling reverse-RPC inside the Executa.
(Superseded: rev 2 ports plan — `LlmGateway`/`TokenBudget` protocols. Kept as fallback if the
binary spike fails: litellm+fastapi+sqlalchemy in PyInstaller too big/broken.)

| File | Change |
|---|---|
| `apps/api/src/json_ai_studio/providers/anna.py` | **new**. `AnnaProvider(DeploymentProvider)`: `name="anna"`, `model_prefix="anna/"`, keyless, `PRICING={}`, reasoning → Anna `thinking` passthrough. |
| `apps/api/src/json_ai_studio/providers/__init__.py` | Register `AnnaProvider` in `PROVIDER_CLASSES`. |
| `apps/api/src/json_ai_studio/settings.py` | `anna_enabled: bool = False` (web never routes to Anna); Executa sets True. |
| `apps/api/src/json_ai_studio/config/deployments.yaml` | `anna` entry: `models: [default]`, `context_tokens`, `supports_tools: true` (emulated), `supports_thinking: true`, no `tpm_input_limit` / `min_call_interval_s`. Disabled unless `anna_enabled`. |
| `apps/api/src/json_ai_studio/db/session_store.py` | Add `set_store()`; services call `get_store()` instead of importing `store` (17 call sites in session/chat/chat_history/diff/version services). |
| `apps/api/src/json_ai_studio/resources.py` | **new**. Package-data reader via `importlib.resources` (PyInstaller-safe); used by `format_hints.py`, `deployment.py`. |
| `apps/api/tests/test_anna_provider.py` | **new**. Provider loads only when enabled; fake `CustomLLM` registered under `anna/` drives one full chat turn through the real gateway (inline + tool loop) → accept → snapshot. |

Gate: full API suite green; web deployments unaffected (anna disabled by default).

**Stage A done 2026-11-12** on `feature/anna-app` (from `release` @ 7cc0e2c5), uncommitted. 306 passed, 18 skipped.
Deviations from the table above:
- Store swap: `store` is now a delegating `_ActiveStore`; `set_store(backend)` swaps behind it. No call-site
  edits in services (they keep `from ..db.session_store import store`).
- `resources.py` dropped: the PyInstaller spike loaded `config/deployments.yaml` via `__file__` fine with `--add-data`.
- Thinking is passed as litellm kwarg `anna_thinking` (False | effort) — the Executa handler reads it from `optional_params`.

## Stage B done 2026-11-12 (uncommitted) — `apps/anna/executas/json-ai-studio/`

Built: `json_ai_studio_plugin.py` (stdio loop), `jstudio/{rpc,anna_llm,aps_store,wiring,tools}.py`,
`executa.json`, tests (7 pass: 6 in-process against a fake Anna host + 1 real subprocess stdio run).
Run: `cd apps/anna/executas/json-ai-studio && uv run pytest -q tests`.

Differences from the table below:
- **No Anna SDK.** `executa-sdk` is not on PyPI (git-only); own ~130-line client `jstudio/rpc.py` instead.
- **No lookup-tool loop on Anna** (`supports_tools: false`): host caps one invoke at 8 sampling calls /
  **32,000 tokens total** / 8,192 output. Turn = one call, input planned ≤ 19.2k tokens
  (`tpm_input_limit: 24000` × 0.8). Larger docs → skeleton prompt or `input_too_large` + `focus_path`.
  `deployment_budget.reset()` at each turn (cap is per invoke, not per minute).
- **Storage scope `tool`**, not `app`; sessions ≤ 48 KB in KV, larger in object storage (presigned PUT/GET).
- `chat_turn` returns the same event list the web SSE stream emits (`{events:[{event,data}]}`), plus
  `host_error` for Anna quota / per-invoke cap; `working_json` dropped from the result above 200 KB.
- stdout is reserved for frames: `sys.stdout` is repointed to stderr at startup (LiteLLM logs to stdout).
- Executa has its own `uv.lock` (path dep on `apps/api`); CI binary build must use this lock.

Not verified yet: `anna-app dev` harness run, real sampling/storage against Anna, PyInstaller build of the real plugin.

## B. Executa — `apps/anna/executas/json-studio/`

| File | Purpose |
|---|---|
| `pyproject.toml` | Project `tool-dev-json-ai-studio`; deps: `executa-sdk` (pip name TBC from examples repo), `deepdiff`; path dep on `../../../api` (import core only). Dev deps: `anna-executa-test`, `pytest`. |
| `json_studio_plugin.py` | Entry: stdio loop, v2 handshake (`initialize`, `capabilities.sampling`), `describe` (tools below, `host_capabilities: ["llm.sample"]`), `health`, `invoke` dispatch, envelope `{success,data|error}`. Logs → stderr only. |
| `jstudio/aps_store.py` | `ApsSessionStore(SessionStore)` — session dict ↔ APS (`scope: app`): `sessions/index` KV; `sessions/<id>.json` file (64 KB KV cap); etag `if_match`. |
| `jstudio/anna_llm.py` | `AnnaSamplingLLM(litellm.CustomLLM)` registered via `litellm.custom_provider_map` as `anna`. `acompletion`/`astreaming` → `sampling/createMessage` on the current invoke's stdio channel (contextvar holds writer + `sampling_token`); explicit `thinking`; when `tools` passed, emulate via `responseFormat: json_object` action protocol and return real `tool_calls`. Host quota error → exception the gateway maps to a quota event (Anna wording). |
| `jstudio/events.py` | SSE event stream → `emit_progress` + final tool result (diffs, explanation, question, too-large sections). |
| `jstudio/tools.py` | Thin handlers calling the **existing services** (`session_service`, `chat_service.chat_event_stream`, `diff_service`, `version_service`, `chat_history_service.clear_chat`, explain via gateway): `create_doc`, `list_docs`, `get_doc`, `chat_turn` (async), `accept_diff`, `reject_diff`, `accept_all`, `reject_all`, `save_version`, `list_versions`, `select_version`, `explain` (async), `clear_chat`, `delete_doc`. |
| `jstudio/wiring.py` | Env before import: `ANNA_ENABLED=1`, huge `ANON_MONTHLY_CREDIT_LIMIT`, no DB/Auth0; `set_store(ApsSessionStore())`; register `AnnaSamplingLLM`. |
| `tests/test_plugin.py` | `anna-executa-test` fixtures, sampling stubbed: describe shape, create → chat_turn → accept → save_version round trip, quota error path. |
| `build/pyinstaller.spec` | `--onedir` build incl. `config/format_notes.json`. |

## Harness run + Stage C done 2026-11-12 (uncommitted)

Harness (`anna-app dev`, real Anna LLM; in-memory storage and `--storage aps`): create/list/get/delete,
chat turn (~2.3 s, ~3.2k tokens), follow-up turn with history, accept all, save version, explain,
`invokeAsync` job with progress, 300 KB document via object storage — all OK.
Fixes from the harness: storage scope `tool` → **`app`** (tool scope needs a manifest declaration);
`storage/get` without `exists` (in-memory backend) tolerated. APS latency: create ~3 s, list ~1 s (several
round trips per save — optimise later).

Stage C as built (differs from the table below):
- `apps/anna/ui/` (Vite + React 19 + Tailwind) → builds into `apps/anna/bundle/` (gitignored).
- **Web `SessionContext.tsx` and all components reused unmodified.** A Vite plugin resolves every
  import of `apps/web/src/lib/api` to `ui/src/anna/api.ts` — same function names/shapes, implemented
  over Executa tools (`ui/src/anna/runtime.ts`: `tools.invoke`, `invokeAsync` + `getJob` polling).
  So no `AnnaSessionContext`, and stage D (web changes) is not needed.
- Executa gained `create_session`, `upload_json`, `restore_versions`; NotFound/Conflict errors are
  prefixed `404: ` / `409: ` so the shared client code keeps its status handling.
- `ui/src/App.tsx`: studio layout without login/workspaces/site nav; versions via a dropdown.
- Shims: `openInWorkspace` (next/navigation), in-memory `localStorage` fallback.
- On a new device `main.tsx` resumes the newest document from `list_docs`.
- Verified in harness with the real UI: load sample → chat chip → diff viewer → Accept All → reload.
  In the in-memory harness a reload loses host storage and the IndexedDB restore path took over.

Done after that (2026-11-12): merged `release` (text edits, Nemotron default) — suites green, UI
re-checked in harness; `build_binary.sh` (darwin-arm64: 51 MB archive / 96 MB unpacked, stdio test passes
against the binary; litellm pinned to 1.89.3 — 1.109 doubled the size); `executa.json` `binary_artifacts`;
`.github/workflows/anna-executa.yml`; ADR-0026; CLAUDE.md.

Tool id minted 2026-11-12: `tool-json-ai-studio-json-ai-studio-nk262zbg` (manifest, executa.json,
plugin, pyproject, `ui/src/anna/runtime.ts`).

Left (manual / outward-facing): register CI as trusted publisher + set repo vars `ANNA_TOOL_ID`,
`ANNA_APP_HOST`; logo + screenshots + privacy URL; `apps push` → `apps cut 0.1.0` → `submit-review` →
`release`; first linux-x86_64 CI build (unverified natively); trim APS round trips; stray dev app `anna`.

## C. Bundle — `apps/anna/`

| File | Purpose |
|---|---|
| `manifest.json` | From scaffold: schema 4, `required_executas` → json-studio tool id, `ui.bundle` static-spa, `external_origins: []`, views `main` (default size ~1200×800, min 900×600), `ui.form_factors: ["desktop"]`. |
| `app.json` | name "JSON AI Studio", tagline, description, category productivity, `bundled_executas` ref → `executas/json-studio`. |
| `package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.js` | Vite + React 19 + Tailwind 3; alias `@web/*` → `../web/src/*`; `next/link` → shim; output → `bundle/`. |
| `src/main.tsx`, `src/App.tsx` | Runtime connect, theme/locale, two-panel layout (chat/upload left, diff/tree right). |
| `src/anna/runtime.ts` | `AnnaAppRuntime.connect()` wrapper + typed `invoke` / `invokeAsync` + job polling with progress. |
| `src/anna/AnnaSessionContext.tsx` | Same context shape as web `SessionContext` (what components consume), backed by Executa tools. |
| `src/shims/next-link.tsx` | `<a>` fallback. |
| `src/__tests__/smoke.test.ts` | `mountBundle` from `@anna-ai/cli/test` smoke test. |
| `README.md` | Dev loop: `anna-app dev`, `validate`, `push`. |

## D. Web app — minimal, enables component reuse

| File | Change |
|---|---|
| `apps/web/src/context/SessionContext.tsx` | Export the context **type** + a `useSession` hook that reads a context object both providers fill (no behaviour change). |
| Components consumed by the bundle (ChatPanel, DiffViewer, JSONTree, UploadPanel, VersionModal, ExplainPanel, TooLargeModal, StatusPill) | Only if they import Next/Auth0/web-only modules directly: move that import behind props. Audit first; list exact edits before changing. |

## E. Repo / docs / CI

| File | Change |
|---|---|
| `docs/adr/0026-anna-app-executa.md` | **new** ADR. |
| `.github/workflows/anna-executa.yml` | **new**. PyInstaller matrix (linux-x86_64, darwin-arm64, windows-x86_64) → `anna-app executa upload-binaries`. Later step; needs PAT secret (manual). |
| `CLAUDE.md` | Add `apps/anna/` to structure + Anna key facts (corpus path, schema 4). |
| `.gitignore` | `apps/anna/bundle/` build output if Vite writes there (keep scaffold `index.html` source elsewhere). |

## Spike result (2026-11-12) — PyInstaller viable

Stub Executa importing `chat_service`, `gateway`, `diff_service`, `version_service` + litellm `CustomLLM`
under `anna/`; real `litellm.acompletion` call routed to the custom handler.

| Build | Unpacked | .tgz | Startup |
|---|---|---|---|
| darwin-arm64 (uv.lock) | 112 MB | 57 MB | ~1.15 s warm |
| linux-x86_64, unpinned, no strip | 271 MB | 129 MB | — |
| **linux-x86_64, uv.lock + strip + excludes** | **93 MB** | **50 MB** | 12–17 s under QEMU (native expected ~1–2 s; verify in CI) |

CI build flags (keep in the workflow):
```
uv export --frozen --no-dev --no-hashes --no-emit-project > requirements.txt
pyinstaller --onedir --strip --paths apps/api/src \
  --add-data "apps/api/src/json_ai_studio/config:json_ai_studio/config" --collect-data litellm \
  --hidden-import tiktoken_ext --hidden-import tiktoken_ext.openai_public \
  --collect-submodules json_ai_studio \
  --exclude-module botocore --exclude-module boto3 --exclude-module asyncpg \
  --exclude-module uvloop --exclude-module alembic --exclude-module uvicorn
rm -rf dist/<name>/_internal/litellm/proxy   # data files only
```
Gotchas: `tiktoken_ext` hidden imports required (else `Unknown encoding cl100k_base`); do **not**
`--exclude-module litellm.proxy` (imported at litellm load via gcs_bucket logging); always build from
`uv.lock` (unpinned litellm was ~3× bigger).

## Order

Spike (PyInstaller size/startup on linux-x86_64) → A (provider + store swap, suite green) → B (Executa + tests, `anna-app dev --llm real`) → C (bundle) → D (only as C needs) → E.
Commit per stage on branch `feature/anna-app` (from `main`/`release` — confirm).

## Not touched

FastAPI controllers, OpenAPI spec (no new HTTP endpoints), Auth0, workspaces, DB, deployments.yaml, web pages.
