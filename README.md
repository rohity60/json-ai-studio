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
