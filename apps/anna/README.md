# JSON AI Studio — Anna App

The Anna App build of JSON AI Studio (slug `json-ai-studio`, ADR-0028).

```
apps/anna/
├── manifest.json, app.json      App manifest (schema 4) and store listing
├── ui/                          React bundle source (Vite). Reuses apps/web/src components
│                                and SessionContext; `lib/api` is swapped for src/anna/api.ts
├── bundle/                      Build output of ui/ (gitignored) — what Anna serves
└── executas/json-ai-studio/     Python Executa: the shared engine (apps/api) over Anna
                                 sampling (LLM) and Anna Persistent Storage (sessions)
```

Nothing here calls the FastAPI backend. LLM calls are billed to the Anna user.

## Develop

```bash
cd apps/anna/ui && npm install --legacy-peer-deps && npm run build   # or: npm run watch
cd apps/anna && anna-app validate --strict
cd apps/anna && anna-app dev --slug json-ai-studio --llm-app-slug json-ai-studio
# real Anna storage instead of the in-memory one: add --storage aps
```

Restart `anna-app dev` after changing Executa Python code (the plugin process is long-lived).

## Test

```bash
cd apps/anna/executas/json-ai-studio && uv run pytest -q tests
```

## Limits to know

- One chat turn = one LLM call: Anna allows 8 calls / 32,000 tokens per tool invoke, 8,192 output
  tokens per call. No lookup-tool loop; large documents use the skeleton prompt or the
  "too large → pick a section" flow.
- Desktop only (Executas do not run on mobile).
