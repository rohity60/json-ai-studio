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
| V-06 | `GET /api/sessions/{id}` — retrieve a session with its working JSON, conversation history, version list | MVP ✅ |
| V-07 | `POST /api/sessions/{id}/versions` — create a named snapshot of the current state | MVP ✅ |
| V-08 | `POST /api/sessions/{id}/diffs/{diff_id}/accept` — apply an approved diff to the working JSON | MVP ✅ |
| V-09 | `POST /api/sessions/{id}/diffs/{diff_id}/reject` — revert the rejected change from working state | MVP ✅ |
| V-10 | `GET /api/sessions/{id}/versions` — list all versions with timestamps | MVP ✅ |
| V-11 | `POST /api/sessions/{id}/versions/select` — select a version snapshot as the new working baseline (see R7–R10 below) | MVP |
| V-12 | `POST /api/sessions/{id}/versions/select` returns full updated session state including `active_version_id` | MVP |

## 5.5 Version Selection — Detailed Requirements

When a user selects a previously created version snapshot, the system must treat it as branching point: the selected snapshot becomes both the current working state AND the new baseline, with a fresh conversation history branch. This enables the user to continue editing from any point in the version tree.

### R7 — Select Version: Set Working + Baseline

- `POST /api/sessions/{id}/versions/select` — accept `{ versionId: string }`.
- Look up the `VersionSnapshot` by `versionId` from the session's `versions` list.
- Set `session["working_json"] = copy(version.json_data)`.
- Set `session["baseline_json"] = copy(version.json_data)`.
- Both must be deep copies (not references to the snapshot's stored data).
- Return updated session state: `{ working_json, baseline_json, versions, active_version_id }`.

### R8 — Select Version: Reset Conversation History

- On version selection, clear `session["conversation_history"]` to start a fresh branch.
- The old conversation history is discarded; the session effectively branches at the selected version.
- This mirrors the behavior after `accept-all` (R3): baseline and working converge, history resets.
- Rationale: selecting a version means "start working from this point forward." Old chat turns are irrelevant to the new branch.

### R9 — Select Version: Track Active Version

- Session gains a new field: `active_version_id: str | None`.
- On select: `session["active_version_id"] = versionId`.
- On new session creation: `active_version_id = None`.
- On upload: `active_version_id = None` (upload resets the branch).
- GET session response includes `active_version_id` so frontend knows which version is active.
- `active_version_id` is nullable: `null` means no version has been selected (default state).

### R10 — Select Version: Validation

- If `versionId` does not exist in the session's versions list → return 404 with error "Version not found".
- If session does not exist → return 404 with error "Session not found".
- If `versionId` matches the currently active version (no-op) → return 200 with unchanged state (idempotent).

### Data Model Update: Session

```python
class Session(BaseModel):
    id: str                            # human-readable name
    working_json: Any                  # current mutable state (after)
    baseline_json: Any                 # stable "before" state; only changes on accept/reject-all or version select
    versions: list[VersionSnapshot]    # historical snapshots
    conversation_history: list[ChatTurn]
    applied_diffs: list[str]           # diff IDs already applied
    active_version_id: str | None      # currently selected version; None = default
    created_at: datetime
    updated_at: datetime
```

### API Endpoint Signature

```
POST /api/sessions/{sessionId}/versions/select
Request:  { "versionId": "v3" }
Response: { "working_json": {...}, "baseline_json": {...}, "active_version_id": "v3", "versions": [...], "conversation_history": [] }
```

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
    id: str                            # human-readable name
    working_json: Any                  # current mutable state (after)
    baseline_json: Any                 # stable "before" state; only changes on accept/reject-all or version select
    versions: list[VersionSnapshot]    # historical snapshots
    conversation_history: list[ChatTurn]
    applied_diffs: list[str]           # diff IDs already applied
    active_version_id: str | None      # currently selected version; None = default (no version selected)
    created_at: datetime
    updated_at: datetime
```

### VersionSnapshot

```python
class VersionSnapshot(BaseModel):
    id: str
    parent_id: str | None             # reference to predecessor
    json_data: Any
    label: str                        # e.g. "original", "v1 - increase timeout"
    created_at: datetime
```

### ChatTurn

```python
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str                      # the message text
    diffs: list[DiffEntry] | None     # attached diff from assistant turn
```

## 9.5 Bidirectional Diff State Management

Backend maintains `baseline_json` alongside `working_json` per session. `baseline_json` = "before" state (stable, only changes on accept/reject-all or version-select). `working_json` = "after" state (mutable, changes on upload, chat, single diff actions).

### R1 — Upload: Return Before + After as Same JSON ✅
- `POST /api/json/upload` — parse uploaded JSON → `data`
- Set `session["baseline_json"] = data`, `session["working_json"] = data`
- Response: `{ "session_id": sid, "before": data, "after": data, "diffs": [] }`

### R2 — Chat: Return Baseline + Working + Unapplied Diffs ✅
- `POST /api/chat` — on SSE `complete` event: `baseline_json` unchanged, `working_json` = LLM result
- `baseline_json` only changes on: accept-all (R3), reject-all (R4), or version select (R7)
- Response: `{ "baseline_json": <baseline>, "working_json": <working>, "diffs": [entries] }`

### R3 — Accept All: Merge Working into Baseline ✅
- `POST /api/sessions/{id}/diffs/accept-all` — `session["baseline_json"] = copy(session["working_json"])`
- Response: `{ "baseline_json": working_copy, "working_json": working_copy, "diffs": [] }`

### R4 — Reject All: Restore Baseline ✅
- `POST /api/sessions/{id}/diffs/reject-all` — `session["working_json"] = copy(session["baseline_json"])`
- Response: `{ "baseline_json": baseline, "working_json": baseline, "diffs": [] }`

### R5 — Accept Single Diff: Apply + Return Updated State ✅
- `POST /api/sessions/{id}/diffs/{diffId}/accept` — apply diff to `working_json`, add diff ID to `applied_diffs`
- Response: `{ "baseline_json": baseline, "working_json": new_working, "diffs": [remaining_diffs] }`

### R6 — Reject Single Diff: Reverse + Return Updated State ✅
- `POST /api/sessions/{id}/diffs/{diffId}/reject` — reverse diff on `working_json`, remove from `applied_diffs`
- Response: `{ "baseline_json": baseline, "working_json": new_working, "diffs": [remaining_diffs] }`

## 10. API Summary (Routes)

| Method | Endpoint                          | Purpose                    |
|--------|-----------------------------------|---------------------------|
| POST      | `/api/sessions`                    | Create a new session       |
| POST      | `/api/json/upload`                 | Upload / parse JSON        |
| POST      | `/api/chat`                        | Send a chat turn (SSE)     |
| POST      | `/api/validate`                    | Validate a JSON blob       |
| POST      | `/api/diff`                        | Compute diff               |
| GET       | `/api/sessions/{id}`               | Get session state          |
| POST         | `/api/sessions/{id}/versions/select` | Select version as working baseline |
| POST      | `/api/sessions/{id}/versions`      | Create version snapshot    |
| POST      | `/api/sessions/{id}/diffs/`        | Apply / reject diffs       |
| GET       | `/api/sessions/{id}/export`        | Download JSON file         |

## 10.5 Version Selection — Unsaved Changes Guard

When the user attempts to select a version, the backend must always succeed. The unsaved-changes guard is a **frontend-only** concern: the frontend must detect if the current `working_json` differs from the last saved baseline, and if so, show a confirmation modal before calling the select endpoint. See frontend requirements for full details.

## 11. Excluded from MVP (Backend)

- Encryption at rest / encryption in transit (HTTPS-only in production)
- Role-based access control (no auth layer in MVP)
- Audit logging
- Multi-file editing endpoints
- Team collaboration endpoints
- Enterprise governance features (approval chains, policy enforcement)
