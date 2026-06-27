# Backend Requirements — JSON AI Studio MVP

Derived from PRD v1.0. Only what the **server / API layer** must implement.
Technical decisions are documented in `docs/adr/`.

---

## 1. Upload & Parsing Service

| # | Requirement | Priority |
|---|-------------|----------|
| P-01 | `POST /api/json/upload` — accept a file or raw JSON body; parse and return structured AST / tree | MVP |
| P-02 | Validate syntax on ingest; return clear error (`line`, `column`, `message`) for invalid JSON | MVP |
| P-03 | Generate a **schema summary** from the parsed structure (top-level keys, nested depth, array lengths) — used to populate chat context | MVP |
| P-04 | Maximum file size: 20 MB (reject with 413 if exceeded) | MVP |

## 2. Conversational Editing API

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | `POST /api/chat` — accept `{ conversation_history, new_message }`; return AI-generated modification plan as structured JSON diff via SSE streaming | MVP |
| C-02 | Conversation history persisted per session; sent to LLM via message body alongside working JSON | MVP |
| C-03 | Session model carries the current working JSON into each turn so the model has fresh state | MVP |
| C-04 | Support natural-language patterns: add fields, remove fields, rename fields, update values, bulk updates, conditional modifications (e.g. "for all services except payment") | MVP |
| C-05 | Timeout for LLM call: 5 s max; return error response on failure | MVP |

## 3. Change Proposal Engine

| # | Requirement | Priority |
|---|-------------|----------|
| E-01 | After processing a chat turn, generate a structured **diff object** representing before / after for each changed field | MVP |
| E-02 | Diff must include: path (JSON Pointer `/ietf/refs`), old_value, new_value, operation (`add`/`modify`/`delete`) | MVP |
| E-03 | Every diff is initially in a **pending** state — not applied until user approves | MVP |

## 4. Validation Engine

| # | Requirement | Priority |
|---|-------------|----------|
| V-01 | `POST /api/validate` — accept a JSON document and return `{ valid: bool, errors: [] }` | MVP |
| V-02 | **Syntax validation**: ensure the input parses as valid JSON (use `json.loads`) | MVP |
| V-03 | Schema validation: required fields, data types, enumeration constraints (configurable via a JSON schema object) — **deferred to future phase** | MVP |
| V-04 | Business rule validation examples: `timeout > 0`, `retryCount <= 10`, mandatory fields populated | MVP |
| V-05 | Run validation automatically after each approved diff before marking it as final | MVP |

## 5. Version Management API

| # | Requirement | Priority |
|---|-------------|----------|
| V-06 | `GET /api/sessions/{id}` — retrieve a session with its working JSON, conversation history, version list | MVP |
| V-07 | `POST /api/sessions/{id}/versions` — create a named snapshot of the current state | MVP |
| V-08 | `POST /api/sessions/{id}/diffs/{diff_id}/accept` — apply an approved diff to the working JSON | MVP |
| V-09 | `POST /api/sessions/{id}/diffs/{diff_id}/reject` — revert the rejected change from working state | MVP |
| V-10 | `GET /api/sessions/{id}/versions` — list all versions with timestamps | MVP |

## 6. Diff Generation API

| # | Requirement | Priority |
|---|-------------|----------|
| D-03 | `POST /api/diff` — accept `{ old: JSON, new: JSON }`; return a structured diff for the frontend to render | MVP |
| D-04 | Support field-level diffs in nested objects and arrays | MVP |

## 7. Export API

| # | Requirement | Priority |
|---|-------------|----------|
| E-04 | `GET /api/sessions/{id}/export` — download the current working JSON as a file | MVP |
| E-05 | Query parameter `?format=minified` returns minified JSON; default is pretty-printed | MVP |

## 8. Performance Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| P-05 | Upload parse: < 2 s for files up to 20 MB | MVP |
| P-06 | Diff generation: < 1 s for 100K+ nodes | MVP |
| P-07 | AI response (LLM call): < 5 s target; gracefully handle latency via SSE streaming | MVP |
| P-08 | Validation: < 2 s per document | MVP |

## 9. Data Model

### Session

```python
class Session(BaseModel):
    id: str                          # human-readable name
    working_json: Any                # current mutable state
    versions: list[VersionSnapshot]  # historical snapshots
    conversation_history: list[ChatTurn]
    created_at: datetime
    updated_at: datetime
```

### VersionSnapshot

```python
class VersionSnapshot(BaseModel):
    id: str
    parent_id: str | None            # reference to predecessor
    json_data: Any
    label: str                       # e.g. "original", "v1 - increase timeout"
    created_at: datetime
```

### ChatTurn

```python
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str                     # the message text
    diffs: list[DiffEntry] | None    # attached diff from assistant turn
```

## 10. API Summary (Routes)

| Method | Endpoint                          | Purpose                   |
|--------|-----------------------------------|---------------------------|
| POST     | `/api/sessions`                   | Create a new session      |
| POST     | `/api/json/upload`                | Upload / parse JSON       |
| POST     | `/api/chat`                       | Send a chat turn (SSE)    |
| POST     | `/api/validate`                   | Validate a JSON blob      |
| POST     | `/api/diff`                       | Compute diff              |
| GET      | `/api/sessions/{id}`              | Get session state         |
| POST     | `/api/sessions/{id}/versions`     | Create version snapshot   |
| POST     | `/api/sessions/{id}/diffs/`       | Apply / reject diffs      |
| GET      | `/api/sessions/{id}/export`       | Download JSON file        |

## 11. Excluded from MVP (Backend)

- Encryption at rest / encryption in transit (HTTPS-only in production)
- Role-based access control (no auth layer in MVP)
- Audit logging
- Multi-file editing endpoints
- Team collaboration endpoints
- Enterprise governance features (approval chains, policy enforcement)
