# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

JSON AI Studio — AI-powered JSON configuration management. Developers/PMs manage JSON configs via natural language chat. OpenAPI-first MVP scaffold.

## Quickstart

```bash
# API (Python 3.12+, FastAPI, uv)
cd apps/api && uv sync && uv run uvicorn src.json_ai_studio.main:app --reload
# → http://localhost:8000, Swagger at /docs

# Web (Next.js 15 app router, React 19, Tailwind 3, TypeScript)
cd apps/web && npm install && npm run dev
# → http://localhost:3000
```

No tests, no linting, no CI. Run `pytest` or `ruff` manually if installed.
Python files: always format with `black .` after editing (install via `uv add --dev black`).

## Structure

```
json-ai-studio/
├── openapi/spec.yaml            ← Single source of truth. 11 endpoints, 16 schemas. OpenAPI 3.1 YAML.
├── apps/api/                    ← FastAPI backend
│     └── src/json_ai_studio/
│           ├── main.py              ← FastAPI app. All 11 endpoints + SSE streaming + LiteLLM integration.
│           ├── models.py            ← Pydantic schemas (canonical wire format per ADR-0011).
│           ├── store.py             ← In-memory dict SessionStore (ADR-0006). Thread-unsafe, no TTL.
│           ├── auth.py              ← Per-session API key auth + sliding-window rate limiter (10 req/min per key).
│           └── utils.py             ← deepdiff-based diff engine + business-rule validation (V-04: timeout > 0, retryCount <= 10).
├── apps/web/                    ← Next.js 15 app router frontend
│     ├── src/
│     │    ├── app/
│     │    │    ├── layout.tsx   ← Root layout. Wraps children in <SessionProvider>.
│     │    │    └── page.tsx     ← Home. Two-panel layout with header, chat/upload tabs, diff preview toggle.
│     │    ├── components/
│     │    │    ├── UploadPanel.tsx  ← Drag-and-drop + textarea for JSON upload.
│     │    │    ├── ChatPanel.tsx    ← SSE chat consumer (thinking → diff(s) → complete phases).
│     │    │    ├── JSONTree.tsx     ← react-json-view-lite wrapper for JSON preview.
│     │    │    ├── DiffViewer.tsx   ← Before/after side-by-side + per-change accept/reject.
│     │    │    └── VersionSidebar.tsx ← Version snapshot list + select toggle.
│     │    ├── context/
│     │    │    └── SessionContext.tsx  ← React context: session lifecycle, SSE chat, diff actions, export. Persists sessionId to localStorage.
│     │    └── lib/
│     │         └── api.ts            ← Minimal fetch-based API client (no retry, no interceptor).
│     └── tailwind.config.ts   ← Tailwind config.
├── docs/adr/                  ← 12 Architecture Decision Records. All tech decisions numbered & dated.
└── openapi/README.md           ← OpenAPI spec conventions.
```

## Key facts

- **OpenAPI-first contract**: `openapi/spec.yaml` (877 lines, 11 endpoints, 16 schemas) is the contract source. Pydantic models in `models.py` implement it verbatim (ADR-0011). Frontend TS types are hand-written mirrors — not auto-generated.
- **Session model**: In-memory dict store (ADR-0006). Each session = working_json + version snapshots + conversation history. No persistence beyond sessionId → localStorage. No TTL.
- **Chat flow**: User NL message → LiteLLM call → field-level diffs → SSE stream: thinking → diff(s) → complete (ADR-0002, ADR-0004). The system prompt in `main.py` embeds the current working JSON as few-shot examples (ADR-0005).
- **Diff engine**: `deepdiff` for backend (ADR-0003); client-side `deep-diff` for DiffViewer. Business rules only (timeout > 0, retryCount <= 10). No JSON Schema validation yet.
- **Error handling**: Fail-fast with 500 + hint string (ADR-0007). No retry logic at MVP.
- **Tech stack decisions**: litellm over direct OpenAI SDK (ADR-0002), react-json-view-lite over alternatives (ADR-0008), sonner for toasts (ADR-0009), lucide-react for icons (ADR-0010).

## API endpoints

From `openapi/spec.yaml` and implemented in `main.py`:
| Method | Path | Purpose |
|--------|------|---------|
| POST   | `/api/sessions` | Create session |
| GET    | `/api/sessions/{id}` | Get session |
| DELETE | `/api/sessions/{id}` | Delete session |
| POST   | `/api/json/upload` | Upload JSON file/body |
| POST   | `/api/chat` (SSE) | NL message → diffs |
| POST   | `/api/sessions/{id}/versions` | Create version snapshot |
| GET    | `/api/sessions/{id}/versions/{vid}` | Get version |
| DELETE | `/api/sessions/{id}/versions/{vid}` | Delete version |
| POST   | `/api/diff/accept` | Accept a diff |
| POST   | `/api/diff/reject` | Reject a diff |
| GET    | `/api/export/{sid}/{vid}` | Export JSON file |

All routes + auth/rate-limit middleware in `main.py`. No separate router/middleware files.

## Frontend architecture

- **SessionContext** (context/SessionContext.tsx): Single source of truth for React state. Wraps all pages in `<SessionProvider>`. Manages create/upload/sendMessage/diff actions/export. Persists sessionId to localStorage only.
- **App shell** (app/page.tsx): Two-panel layout. Left panel = ChatPanel + UploadPanel (tabbed). Right panel = DiffViewer ↔ JSONTree (toggleable preview tabs). Top bar has New Session, Sidebar toggle. VersionSidebar (slide-out) shows version history.
- **ChatPanel**: SSE consumer. Subscribes to `/api/chat` streaming endpoint. Renders thinking → diff(s) → complete phases. Accept/reject buttons per diff.
- **DiffViewer**: Side-by-side before/after + list of changes with accept/reject per entry. Uses `deep-diff` client-side.
- **No form libraries**: All inputs are plain `<input>` / `<textarea>`. No Zod, no React Hook Form.

## Important files

- `openapi/spec.yaml` — Edit first for any contract change. 16 schemas define the wire format.
- `apps/api/src/json_ai_studio/main.py` — All endpoints. System prompt construction (+ LiteLLM call). SSE generator. ~500 lines, one big file.
- `apps/api/src/json_ai_studio/models.py` — Pydantic models. One shot at spec.yaml field names. Update when spec changes.
- `apps/api/src/json_ai_studio/store.py` — In-memory dict. 30 lines. Replace with DB later (ADR-0006).
- `apps/api/src/json_ai_studio/auth.py`   — Per-session API key auth + sliding-window rate limiter.
- `apps/api/src/json_ai_studio/utils.py` — `compute_diff()` (deepdiff) + `validate_document()` (business rules).
- `apps/web/src/context/SessionContext.tsx` — React context. All state + API calls + SSE streaming logic. ~200 lines.
- `apps/web/src/app/page.tsx` — App shell. Layout wiring for all components.

## Dev workflow

1. Edit `openapi/spec.yaml` for contract changes.
2. Update Pydantic models (`models.py`) and TS types (hand-written in frontend) to match.
3. Write ADR for architectural decisions (>10 already exist).
4. Validate locally: API at `:8000/docs`, Web at `:3000`.

## Editing rules

**Rule: # CRITICAL WORKFLOW FOR INDENTATION ISSUES:
1. When you read Python files, note the exact indentation rule used (e.g., 4 spaces).
2. When editing, do not attempt large string matches if you suspect the linter modified whitespace.
3. Immediately after any edit, run your `lint-and-validate` tool.
4. If the linter fixes indentation, you MUST completely reread the file before making your next edit to update your memory cache.

**Rule: # CRITICAL WORKFLOW FOR PYTHON EDITS:
1. Every time you read a file, always use line numbers. Before reading First Always format Python files with `black .` and then read he file . Install via `uv add --dev black` 
2. When making an edit, use line-based patching tools instead of full-string replacement.
3. Immediately after editing a file, run the project linter/formatter.
4. IMPORTANT: Do not assume you know the state of the file after the linter runs. You MUST run the file-reading tool again to refresh your memory cache with the linter's auto-fixes before attempting a secondary edit.
5. do not use default string matching tool for python files edits at all !!

Claude Code's `Edit` tool does byte-level exact-string matching on the surrounding file. It fails when whitespace differs even by one character. This project's Python files use non-standard indentation depths (tabs, 5-space docstrings, 9-space nested dicts). Edit is fragile here.

**Rule: Use Edit for <10 lines only. Use Write for everything else.**
- `Edit` — typos, single-line changes, adding one function at end of file.
- `Write` — replacing any function body (>5 lines), multi-function rewrites, or when Edit fails twice on the same file.
- Never interleave Bash reads between a Read and Write on the same file.
- When Edit fails twice: abort, read the full file fresh, then use Write to overwrite.
-  Always format Python files with `black .` after editing. Install via `uv add --dev black`.

## Notes

- MVP scaffold only. No tests,  no CI/CD, no persistence (beyond localStorage sessionId).
- Session store is a plain Python dict (ADR-0006). Swap for disk/DB later.
- LiteLLM uses mock fallback when no API key configured (ADR-0002).
- All ADRs are in `docs/adr/`. Read before making decisions that contradict them.
