# 0012-openapi-yaml-as-machine-readable-contract-spec-at-project-root

**Date**: 2026-06-21
**Status**: Accepted

## Context

We need a machine-readable contract format that both frontend and backend implement against. Example JSON fixtures are lightweight but offer no type enforcement or codegen capability. We want to be able to auto-generate TypeScript types from the contracts later (`json-schema-to-typescript`, `openapi-typescript`), which requires a formal schema format.

The OpenAPI 3.1 YAML spec is the industry standard for this: it's machine-readable, human-readable, supports enums and required/optional fields, generates interactive docs (Swagger UI / Redoc), and has mature codegen tooling in both Python (via `prance` or `openapi-python-client`) and JavaScript/TypeScript.

## Decision: OpenAPI YAML Monolith at Project Root (`openapi/`)

Use a **single monolithic OpenAPI 3.1 YAML file** saved at the project root under `openapi/`.

### Directory Structure

```
json-ai-studio/
├── openapi/
│     └── spec.yaml              ← ALL API contracts in one file
├── docs/adr/                    ← architectural decisions
├── apps/
│      ├── api/...
│      └── web/...
└── ...
```

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **Monolithic OpenAPI YAML at `openapi/spec.yaml`** (chosen) | Single file to read, single git log entry. Simple for MVP scale (~4 interfaces, ~10 endpoints). Easy to generate Swagger UI from one file. Codegen tools accept a single spec file out of the box. | Becomes large as APIs grow; hard to find specific paths in a big file. All endpoints live in one place — good for overview, bad for parallel editing by multiple devs. | Not chosen later if we exceed ~20 endpoints and need team parallel editing. For MVP, this is fine. |
| **Split OpenAPI files** (`openapi/chat.yaml`, `openapi/sessions.yaml`, etc.) + a root index that references them | Parallel editing by multiple developers. Each file focuses on one domain. Easier to grep for specific endpoints. | More boilerplate: each file needs its own `paths:` and shared component sections. Codegen tools may not handle split files well without custom config. Overhead for MVP's small API surface. | Not chosen yet — defer to a later ADR if we need multi-developer parallel editing on the spec. |
| **JSON format instead of YAML** | Native JSON is closer to our wire format; some codegen tools prefer it. | Less human-readable: no comments, stricter whitespace rules, more brittle in git diffs. | Not chosen — YAML supports inline comments which are invaluable for documenting contract intent. Also cleaner for reading/writing by humans. |

## Monolithic OpenAPI Structure

The file will be organized as follows:

```yaml
openapi: "3.1.0"
info:
  title: JSON AI Studio API
  version: "0.1.0"
servers:
  - url: http://localhost:8000
    description: Local development server

paths:
  # -- Session Management --
  /api/sessions:
    post:
      summary: Create a new session
      ...
  /api/sessions/{id}:
    get:
      summary: Get session state
      ...
  /api/sessions/{id}/versions:
    get:
      summary: List all versions
      ...
    post:
      summary: Create a version snapshot
      ...
  /api/sessions/{id}/diffs/{diffId}/accept:
    post:
      summary: Apply an approved diff
      ...
  /api/sessions/{id}/diffs/{diffId}/reject:
    post:
      summary: Revert a rejected diff
      ...
  /api/sessions/{id}/export:
    get:
      summary: Download JSON as file
      ...

  # -- JSON Upload & Parsing --
  /api/json/upload:
    post:
      summary: Upload or paste JSON for parsing
      ...

  # -- Chat (SSE Streaming) --
  /api/chat:
    post:
      summary: Send a chat turn; stream SSE response
      responses:
        thinking: { type: "thinking", text: string }
        diff: { type: "diff", entry: DiffEntry }
        complete: { type: "complete", working_json: Any, explanation: string }

  # -- Validation --
  /api/validate:
    post:
      summary: Validate a JSON document
      ...

  # -- Diff Generation --
  /api/diff:
    post:
      summary: Compute diff between two JSON documents
      ...

components:
  schemas:
    # All shared types here:
    Session:          # data model from requirements.md
    VersionSnapshot:   # data model from requirements.md
    ChatTurn:          # data model from requirements.md
    DiffEntry:         # { path, operation, old_value, new_value }
    ValidationError:   # { path?, message }
    Error:             # { error, hint? }
    # ... and all request/response body schemas for each endpoint
```

## Codegen Use Cases

| Direction | Tool | Output |
|-----------|------|--------|
| Backend Pydantic models from OpenAPI | `openapi-python-client` or `prance` + manual refinement | Python models that match spec exactly |
| Frontend TypeScript types from OpenAPI | `openapi-typescript` | `.ts` type definitions with full schema inference |
| Interactive API docs | `swagger-ui-express` (FastAPI) or Redoc Standalone | Auto-generated from the YAML — no extra effort to maintain |

For MVP, we won't auto-generate code yet. But having a valid OpenAPI 3.1 spec means we can run either codegen direction at any time without rewriting contracts.

## Consequences

### The good
- Machine-readable contract → future-proof for codegen (both Pydantic models and TypeScript types)
- One file to read, one file to diff — clear git history of all API changes
- OpenAPI YAML supports inline comments for documenting intent (impossible in JSON)
- Standard format: every toolchain understands it (codegen, mock servers, test generators, etc.)
- Auto-generates interactive Swagger UI from the same file — no separate docs effort

### The bad
- Monolithic file becomes hard to navigate once APIs grow beyond ~10 endpoints
- All developers editing specs must coordinate in one file; git merge conflicts likely with parallel API changes
- YAML indentation-sensitive — easy to introduce subtle errors (but YAML validators catch these early)

## References

- Related ADR: [#0011](0011-api-contracts-per-interface-with-pydantic-as-source-of-truth.md) (Pydantic models as source of truth; OpenAPI spec will be the canonical machine-readable version)
- Related ADR: [#0004](0004-sse-streaming-over-full-json-or-hybrid-for-chat-responses.md) (SSE streaming format defined in the `/api/chat` path)
