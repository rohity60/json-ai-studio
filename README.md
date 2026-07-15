# JSON AI Studio

AI-powered configuration management platform — enable developers, product managers, and solution architects to create, modify, validate, and manage JSON configurations through natural language conversation.

## Project Structure

```
json-ai-studio/
├── README.md                  ← This file: overview, quickstart, links
├── docs/
│     └── adr/                 ← Architecture Decision Records (all tech decisions)
│         ├── 0001-record-tech-decisions-with-adrs.md
│         ├── 0002-litellm-over-openai-sdk-for-llm-integration.md
│         ├── 0003-deepdiff-over-native-diff-for-backend-engine.md
│         ├── 0004-sse-streaming-over-full-json-or-hybrid-for-chat-responses.md
│         ├── 0005-few-shot-prompt-strategy-over-instruction-only-for-llm-diff-generation.md
│         ├── 0006-global-session-store-over-explicit-session-lifecycle-for-in-memory-storage.md
│         ├── 0007-fail-fast-error-handling-over-retry-pattern-for-llm-calls.md
│         ├── 0008-cashify-react-json-view-over-native-or-alternatives-for-tree-rendering.md
│         ├── 0009-sonner-over-react-hot-toast-or-native-for-toasts.md
│         └── 0010-lucide-react-over-native-or-alternatives-for-icon-library.md
├── apps/
│     ├── api/                 ← FastAPI backend (Python 3.12+)
│     │     └── pyproject.toml
│     │     └── src/json_ai_studio/main.py
│     │     └── ai/feature/mvp/requirements.md   ← Backend feature requirements
│     └── web/                 ← Next.js frontend (React + Tailwind)
│           ├── package.json
│           ├── tsconfig.json
│           ├── next.config.mjs
│           ├── src/app/layout.tsx
│           ├── src/app/page.tsx
│           └── ai/feature/mvp/requirements.md   ← Frontend feature requirements
└── (root)
```

## Quickstart

### API (Backend)

```bash
cd apps/api
uv sync                         # install dependencies
uv run uvicorn src.json_ai_studio.main:app --reload    # starts on :8000, /docs auto-generated
```

### Web (Frontend)

```bash
cd apps/web
npm install && npm run dev      # starts on :3000
```

## Configuration (environment variables)

Both apps read config from env files that are **gitignored** — copy the checked-in examples and fill in values:

```bash
cp apps/api/.env.example apps/api/.env          # backend
cp apps/web/.env.example apps/web/.env.local    # frontend
```

### Backend — `apps/api/.env`

All variables are optional, but **chat and explain need at least one LLM provider configured** — set one (or more) of the keys below. Which providers/models are active is controlled by the deployment registry at `apps/api/src/json_ai_studio/config/deployments.yaml` (ADR-0016); a deployment whose key is missing or empty is disabled automatically at load time.

| Variable | Purpose |
|----------|---------|
| `GOOGLE_AI_STUDIO_API_KEY` | Google AI Studio (Gemini/Gemma) key — create one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Enables the `google_ai_studio` deployment. |
| `OPENROUTER_API_KEY` | OpenRouter key — create one at [openrouter.ai/keys](https://openrouter.ai/settings/keys). Enables the `openrouter` deployment (free-tier models available). |
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM key. Enables the `nvidia_nim` deployment (disabled by default in the registry). |
| `OLLAMA_BASE_URL` | Local/remote Ollama endpoint, e.g. `http://localhost:11434`. Unset disables the `ollama_local` deployment. |
| `GENERAL_API_KEY` | Shared anonymous quota-pool key (default `dev-default-key`). |
| `DATABASE_URL` | Async Postgres DSN, e.g. `postgresql+asyncpg://json_ai:json_ai@localhost:5433/json_ai_studio`. Unset → anonymous-only mode (login returns 503). Run migrations with `uv run alembic upgrade head`. |
| `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` | Auth0 tenant domain (no scheme) + API identifier. Together with `DATABASE_URL` they enable optional login (ADR-0015). |
| `ANON_*`, `USER_*` quota knobs | Credit / token / request-rate limits for anonymous and logged-in users — defaults in `settings.py`. |
| `LOG_LEVEL`, `LOG_DIR`, `LOG_*` | Logging (ADR-0017). `LOG_LEVEL=DEBUG` logs full payloads (working JSON, prompts, LLM output, diffs). |

See [apps/api/.env.example](./apps/api/.env.example) for the full annotated list with defaults.

### Frontend — `apps/web/.env.local`

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_BASE` | Backend API base URL. Dev: `http://localhost:8000/api`. Prod: `/api` (reverse-proxied). |
| `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` | Auth0 Regular Web Application credentials (optional login). |
| `AUTH0_SECRET` | Session-cookie encryption secret — generate with `openssl rand -hex 32`. |
| `AUTH0_AUDIENCE`, `AUTH0_SCOPE` | Must match the backend's Auth0 API identifier, or tokens come back opaque and fail JWT validation. |
| `APP_BASE_URL` | Where this app runs; the Auth0 callback URL must be `<APP_BASE_URL>/auth/callback`. |

See [apps/web/.env.example](./apps/web/.env.example) for the annotated list.

## Architecture Overview

```
┌──────────────────────┐   HTTP (SSE streaming)   ┌──────────────────────┐
│    apps/web          │ ──────────────────────►   │   apps/api           │
│    Next.js + React   │                           │   FastAPI + litellm  │
│                      │                           │                      │
│  • JSON Upload UI     │    POST /api/chat (SSE)   │  • LLM Integration   │
│  • Chat Workspace     │  ──────────────────────►  │  • Diff Engine       │
│  • Diff Viewer        │   thinking → diff × N     │  • Validation Engine │
│  • Version Sidebar    │   → complete              │  • Session Manager   │
│  • Export Buttons     │                           │                      │
└──────────────────────┘                           └──────────────────────┘
```

## Documentation

| Doc | Purpose |
|-----|---------|
| [ADR README](./docs/adr/README.md) | All architectural decisions, one per file, numbered & dated |
| [Backend Requirements](./apps/api/ai/feature/mvp/requirements.md) | WHAT the backend API must implement (derived from PRD v1.0) |
| [Frontend Requirements](./apps/web/ai/feature/mvp/requirements.md) | WHAT the frontend UI must implement (derived from PRD v1.0) |

## License

Licensed under the Apache License, Version 2.0 — see [LICENSE](./LICENSE).
