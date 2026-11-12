# Anna App port — plan (rev 3, 2026-11-11)

Goal: ship JSON AI Studio as an Anna App → Founding Builder grant + 70% revenue share.
**Decision (rev 3): Executa from day one; the Anna app never calls our FastAPI backend.**
**Decision (2026-11-12): Anna = another LLM provider (`providers/anna.py`, litellm custom provider
`anna/` → sampling). Gateway/planner/tool loop unchanged. See `migration-files.md` stage A.**

## Status (2026-11-11)

- Anna account + Verified Developer active. CLI `@anna-ai/cli@0.1.64` installed, `anna-app login` done.
- App created in Developer Console, **slug `json-ai-studio`** (immutable). No version/bundle yet.

## Docs for coding agents (use these, not memory)

- Anna's LLM corpus: `https://anna.partners/llms-full.txt` (~900 KB, built 2026-11-06) + index `llms.txt`.
  Local copy: `bash apps/web/ai/feature/anna-app/fetch-anna-docs.sh` → `.anna-docs/` (gitignored —
  third-party docs). Grep before writing Anna code. Key pages: "Host API vs Executa Tool", "Sampling",
  "Agent Sessions", "Persistent Storage (APS)", "Binary Distribution", "Common Pitfalls",
  "App Manifest", "Bundling Executas", "App UI Host API", "Testing the Plugin".
- No official "migrate existing web app" playbook. Closest: forum t/442 (port recipe), t/177 (Cloud
  Agent: never `localhost` between bundle and Executa), t/380 (pre-release inspection guide for AI
  agents — run before submit), t/140 (PyInstaller binary packaging), repo
  `github.com/whtcjdtc2007/anna-executa-examples` (`examples/python/executa-agent-demo`, `sdk/python/executa_sdk`).
- Conflicts: forum posts use manifest schema 2 / `ui.host_api.tools`; corpus says schema 4, fields dropped.
  Trust corpus + `anna-app validate`.

## Program rules that matter

- **Qualified App MAU** = unique signed-in Anna users with ≥1 Qualified App Run (primary function,
  non-trivial result) per UTC month. Anna's server-side records are the source of truth.
  Dev/team/QA accounts, bots, failed runs don't count.
- **Tiers** (monthly, highest only): E 200+ $50 · D 500+ $100 · C 1k+ $200 · B 4k+ $1,000 ·
  A 10k+ $2,500 · S 20k+ $5,000.
- **Qualification window Sep 1 – Nov 30, 2026**: published + 200 MAU in one month. Only November left.
  Review "normally 3–5 business days". Real risk of missing founding status; rev share applies regardless.
- Monthly maintenance update required. No paying users for runs. One grant per Builder Portfolio/month.
- **Revenue share**: 70% of eligible usage profit on Anna paid credits; daily T+1; payout ≥ $50.
  BYOK counts toward MAU (earning unstated).

## Architecture

```
Anna iframe bundle (UI + orchestration)            Executa "json-studio" (Python, stdio JSON-RPC)
  anna.tools.invokeAsync("chat_turn", {doc_id, msg}) ──► plan turn (prompting, turn planner logic)
  poll getJob / progress events  ◄── emit_progress ──    sampling/createMessage  ─► Anna LLM (user CU)
                                                         [lookup loop: JSON-mode actions → json_tools]
                                                         expand bulk ops, compute diffs, guard
                                                         persist session → APS (scope app)
  anna.tools.invoke("accept"/"reject"/"version"...) ──► apply diffs / snapshots → APS
  anna.storage.get (read-only views, doc list)
```

Why this satisfies Anna's "Host API vs Executa" guidance: the Executa is justified by heavy/stateful
Python logic we already own (deepdiff, bulk edits, JSON lookup tools on multi-MB docs) — and it still
reverse-RPCs LLM + storage through the host (no own keys, no own storage). LLM via sampling → user's
Anna model + CU billing → counts as Anna run (MAU) + rev share.

### Hard platform limits to design around

| Limit | Value | Impact |
|---|---|---|
| Sampling `maxTokens` | 8,192 | Fine for diff JSON; huge bulk rewrites must use `bulk` ops |
| Sampling `messages` | ≤ 64 | Chat-history budget must cap turns (already does) |
| Sampling tools | none (agent sessions only use host tools) | Lookup loop (ADR-0024) re-done as JSON-mode action protocol (`responseFormat: json_object`) in our own loop |
| Sync `tools.invoke` | ≤ 90 s | Chat turns use `tools.invokeAsync` (job, progress via `emit_progress`, needs `invoke_id` binding) |
| `invokeAsync` args | ≤ 64 KB | Never pass the document in args; pass `doc_id`, doc lives in APS |
| APS KV value | 64 KB advisory | Working JSON + versions in APS **files** (`files/*`, 20 MiB/object); KV only for small index/metadata |
| Stdio frame | 16 MiB | Results return diffs + paths, not whole docs |
| Platform reach | only where Anna runtime installed (desktop local agent or Cloud Agent); not mobile | `ui.form_factors: ["desktop"]` |
| Cloud Agent | Linux microVM, user's Python not guaranteed | Ship PyInstaller binaries: `linux-x86_64` (required for Cloud Agent), `darwin-arm64`, `windows-x86_64` |
| Executa process | may restart any time; `$EXECUTA_HOME/$EXECUTA_DATA` wiped on upgrade | No in-process state that matters; APS is truth |

Thinking: sampling `thinking` defaults **off**; reasoning tokens count inside `maxTokens` (8,192). Map our
deployment `reasoning` level → explicit `thinking` per call (planner: off/low; never let thinking eat the
diff budget — empty text + `stopReason: maxTokens` = thinking ate it).

Protocol: v2/v2.1 handshake (`initialize`, `capabilities.sampling = {}`), declare `host_capabilities`
`llm.sample` (+ `llm.agent.auto` only if we use agent sessions). Logs → stderr only, never stdout.

## Code changes

### 1. Reusable Python core (no FastAPI/DB/litellm)

Already pure and importable: `utils.py`, `diff_utils.py`, `bulk_edits.py`, `json_tools.py`, `json_trim.py`,
`preview.py`, `format_hints.py` (+ `config/format_notes.json`), `prompting.py` (only depends on `get_settings`).
Coupled (need Executa-side equivalents or a seam): `services/chat_service.py` (store, gateway, SSE),
`services/turn_planner.py` + `services/chat_history_service.py` (`litellm.token_counter/get_model_info`,
deployment budget, store).

- Refactor: split `chat_service` into pure functions `build_turn_messages(...)` and `apply_model_output(...)`
  (parse → bulk expand → diffs → edit guard) that take plain dicts, no store/gateway. FastAPI path keeps
  calling them → no behaviour change for web (existing tests must stay green).
- Token counting seam: `count_tokens(messages)` with litellm in API, `len(chars)/4` heuristic in Executa.
- Executa `pyproject.toml` path-depends on `apps/api`; PyInstaller bundles only imported modules.
  Extract to `packages/jas-core/` later only if binary size/deps hurt.

### 2. Executa — `apps/anna/executas/json-studio/`

- `json_studio_plugin.py`: stdio loop on `executa_sdk` (`SamplingClient`, storage client, `bind_invoke`,
  `emit_progress`). `describe` tools:
  - `create_doc {name, json}` (from upload) → `doc_id`  *(upload > 64 KB: iframe `anna.upload` / APS file path)*
  - `chat_turn {doc_id, message, focus_path?}` (async) → `{turn_id, diffs[], explanation, question?}`
  - `accept_diff` / `reject_diff` / `accept_all` / `reject_all {doc_id, diff_ids?}`
  - `save_version {doc_id, label}` / `select_version {doc_id, version_id}` / `list_versions`
  - `explain {doc_id}` (async) → markdown
  - `clear_chat {doc_id}`
- APS layout (`scope: app`, per user): `docs/index` (KV, small) ·
  `docs/<doc_id>/working.json` · `docs/<doc_id>/versions/<vid>.json` · `docs/<doc_id>/chat.json` (files).
  Writes use `if_match`/etag for concurrency.
- Lookup loop: model replies `{"action":"search|query|read", ...}` or `{"final": {...}}` via JSON mode;
  max 4 rounds (same as ADR-0024); progress event per round.
- Errors → friendly codes (`quota_exceeded` from host → "out of Anna credits"; never raw exception text, cf. #17).
- Tests: `anna-executa-test` fixtures (`executa_session`, `executa_invoke`) with stubbed sampling;
  round-trip chat_turn → accept → version.

### 3. Bundle — `apps/anna/` (Vite + React + Tailwind → `bundle/`)

- Scaffold `anna-app init json-ai-studio --slug json-ai-studio`; keep its `manifest.json`/`app.json`/executa wiring,
  replace bundle with Vite output.
- Reuse `apps/web/src/components/*` (ChatPanel, DiffViewer, JSONTree, UploadPanel, VersionModal,
  ExplainPanel, TooLargeModal, StatusPill) via Vite alias; shim `next/link`; drop Auth0, workspaces, trackers.
- New `AnnaSessionContext` (same interface as `SessionContext`) backed by `anna.tools.invoke/invokeAsync`
  + `anna.storage`; components stay transport-agnostic.
- Theme/locale from `AnnaAppRuntime.connect()` (`onThemeChange` → `<html data-theme>`).
- `manifest.json` schema 4, `required_executas` → bundled `json-studio`, `ui.form_factors: ["desktop"]`,
  **no `external_origins`**. `anna-app validate --strict` green.
- Listing primary function: "edit JSON via chat → reviewable diffs" (defines a Qualified Run).

### 4. Packaging / CI

- GitHub Actions: PyInstaller `--onedir` per platform (linux-x86_64 mandatory) → `anna-app executa upload-binaries`
  (works for private and public repos). Follow forum t/140 + corpus "Binary Distribution".
- `anna-app apps push` on every merge (draft); `apps cut x.y.z` + `submit-review` manually.

### 5. ADR

- ADR-0026 "Anna App: Executa-hosted core, host-mediated LLM + storage" — records this decision,
  limits table, and that web/FastAPI path is unchanged.

## Manual actions (you)

Done: account, developer access, CLI install + login, slug `json-ai-studio`.

Now:
1. Builder Discord (discord.gg/7ftTdsdMMz) — ask: (a) is PyInstaller binary for Cloud Agent still the
   recommended path, or does Cloud Agent run `uv` Python Executas from source? (b) BYOK earns rev share?
   (c) where are the 1,000 dev tokens?
2. DoraHacks hackathon 2349 — apply if required for the grant (check in browser).
3. Listing assets: description, 256×256 logo, screenshots, homepage/support/privacy URLs.
   Privacy: JSON stored in user's Anna storage; LLM via Anna; no data sent to our servers.
4. Payout prep: identity docs + PayPal/Stripe/bank.

After build (target submit ≤ Nov 18):
5. `anna-app dev` end-to-end yourself, incl. a Cloud Agent install of the released binary.
6. Run forum t/380 inspection checklist (hand it to Claude).
7. `anna-app apps push` → `apps cut 0.1.0` → `apps submit-review` → on approval `apps release 0.1.0`.
8. November acquisition push; keep proof of campaigns. Monthly: one real update; check Earnings.

## Open questions

- Cloud Agent Python vs binary (manual action 1a) — affects CI work, not code.
- Exact per-user APS quota (bytes/entries) — large docs + 5 versions could hit it.
- Sampling model quality for our diff JSON on user-chosen (possibly weak) models — may need
  `modelPreferences` hints; test with cheapest default model.
