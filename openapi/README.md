# OpenAPI — JSON AI Studio API Contracts

Monolithic [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0) YAML spec at `spec.yaml`.

## File Structure

```
openapi/
├── spec.yaml                    ← The single source of truth for all API contracts
└── README.md                    ← This file
```

## Usage

### Generate Python Pydantic Models (Backend)

After modifying `spec.yaml`, regenerate Pydantic models:

```bash
pip install openapi-python-client
openapi-python-cli generate \
  --path openapi/spec.yaml \
  --output-dir apps/api/src/generated
```

Or manually: copy schemas from the spec and translate to Pydantic `BaseModel` classes.

### Generate TypeScript Types (Frontend)

Generate typed fetchers and types for the frontend:

```bash
npx openapi-typescript-cli openapi/spec.yaml -o apps/web/src/api/generated.ts
```

Or manually: copy schemas from the spec and translate to TypeScript interfaces with `@see` comments.

### Preview in Swagger UI

The FastAPI app automatically serves generated Swagger UI at `/docs`:

```bash
uv run uvicorn src.json_ai_studio.main:app --reload
# Then visit http://localhost:8000/docs
```

This reads directly from the same Pydantic models that implement the OpenAPI spec.

### Mock Server

Generate a mock server for frontend development while the backend is in-progress:

```bash
pip install prism
npx prism mock openapi/spec.yaml
# Mock server starts at http://localhost:4000
```

## Schema Index

| # | Schema | Purpose |
|---|--------|---------|
| 1 | `Session` | Core domain model — full session state |
| 2 | `VersionSnapshot` | Immutable point-in-time JSON snapshot |
| 3 | `ChatTurn` | Single chat message with role and optional diffs |
| 4 | `DiffEntry` | Wire contract — one field-level change (add/modify/delete) |
| 5 | `ValidationError` | Wire contract — one validation error with path and message |
| 6 | `Error` | Wire contract — all error responses share this shape |
| 7 | `CreateSessionRequest` | POST /api/sessions request body |
| 8 | `SessionResponse` | Session state returned by GET and POST endpoints |
| 9 | `CreateVersionRequest` | POST /api/sessions/{id}/versions request body |
| 10 | `ChatRequest` | POST /api/chat request body (the core chat payload) |
| 11 | `UploadResponse` | POST /api/json/upload response (parsed tree + session ID) |
| 12 | `SchemaSummary` | Metadata about the uploaded JSON structure |
| 13 | `ValidateRequest` | POST /api/validate request body |
| 14 | `ValidateResponse` | POST /api/validate response (valid/invalid with error list) |
| 15 | `DiffAcceptResponse` | POST .../diffs/{id}/accept response |
| 16 | `DiffRejectResponse` | POST .../diffs/{id}/reject response |

## Endpoint Index

| # | Method | Path | Summary |
|---|--------|------|---------|
| 1 | POST | `/api/sessions` | Create a new session |
| 2 | GET | `/api/sessions/{sessionId}` | Get session state |
| 3 | GET | `/api/sessions/{sessionId}/versions` | List all versions |
| 4 | POST | `/api/sessions/{sessionId}/versions` | Create version snapshot |
| 5 | POST | `/api/sessions/{sessionId}/diffs/{diffId}/accept` | Apply approved diff |
| 6 | POST | `/api/sessions/{sessionId}/diffs/{diffId}/reject` | Revert rejected diff |
| 7 | POST | `/api/json/upload` | Upload or paste JSON for parsing |
| 8 | POST | `/api/chat` | Send chat turn (SSE streaming) |
| 9 | POST | `/api/validate` | Validate a JSON document |
| 10 | POST | `/api/diff` | Compute diff between two JSON documents |
| 11 | GET | `/api/sessions/{sessionId}/export` | Download JSON file for a session |

## Development Workflow

When changing the OpenAPI spec:

1. **Edit `spec.yaml`** — update schemas, add endpoints, modify response shapes
2. **Update both implementations** — backend Pydantic models and frontend TypeScript types must stay in sync
3. **Add an ADR** if the change is architectural (new field, new endpoint pattern) — see `docs/adr/`
4. **Document the contract** — all examples in spec.yaml should be realistic JSON that matches PRD requirements
