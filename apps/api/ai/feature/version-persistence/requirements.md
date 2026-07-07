# Backend Requirements — JSON AI Studio Version Persistence Feature

Abstract session storage behind an interface and let a browser-cached workspace be restored into a fresh session after a backend restart. Only what the **server / API layer** must implement.

---

## 1. Storage Abstraction

| # | Requirement | Priority |
|---|-------------|----------|
| S-01 | Replace the module-level dict functions in `store.py` with a `SessionStore` abstract base class. | MVP |
| S-02 | Provide `InMemorySessionStore(SessionStore)` — the only implementation for MVP. Dict-backed, no TTL. | MVP |
| S-03 | Interface methods are **async**: `create_session`, `get_session`, `save_session`, `list_sessions`, `delete_session`. Async so a future DB driver (asyncpg / async SQLAlchemy) slots in without an interface break. | MVP |
| S-04 | Expose a module-level singleton `store: SessionStore` plus `get_store()`. Swapping to a DB backend = one new class + one line. | MVP |
| S-05 | `create_session` returns the full session dict (not just the id), matching what a DB layer would return. | MVP |
| S-06 | Granularity is sessions-only: version snapshots stay embedded in the session dict. A DB impl can normalize them into a child table behind the same interface. | MVP |
| S-07 | Bundled fixes: set real ISO `created_at` / `updated_at` at creation (were `""`); include `active_version_id: null` in new sessions. | MVP |

---

## 2. Layered Structure (controller → service → db)

| # | Requirement | Priority |
|---|-------------|----------|
| L-01 | `main.py` becomes a thin app factory (~40 lines): FastAPI init, CORS, `include_router` per controller. | MVP |
| L-02 | `controllers/` — one APIRouter per resource (health, sessions, versions, uploads, chat, diffs, explain). Parse request, call service, map domain errors → HTTP codes. Auth via `Depends(require_api_key)` per route. | MVP |
| L-03 | `services/` — business logic; the only layer that touches the store. Never raises `HTTPException`. | MVP |
| L-04 | `services/errors.py` — domain exceptions: `NotFoundError → 404`, `ConflictError → 409`, `InvalidInputError → 400`. | MVP |
| L-05 | `db/session_store.py` — the `SessionStore` ABC + `InMemorySessionStore` + singleton. Old `store.py` deleted. | MVP |
| L-06 | All endpoint response shapes stay byte-identical (the frontend depends on them). | MVP |

---

## 3. Restore Endpoint

| # | Requirement | Priority |
|---|-------------|----------|
| R-01 | `POST /api/sessions/{sessionId}/versions/restore` — bulk-restore cached snapshots into a session. | MVP |
| R-02 | Body `RestoreVersionsRequest`: `versions: [VersionSnapshot]` (required, ≤100), optional `working_json`, `baseline_json`, `active_version_id`. | MVP |
| R-03 | Snapshot `id` / `parent_id` / `label` / `created_at` preserved verbatim so the browser cache round-trips losslessly. | MVP |
| R-04 | `working_json` given → deep-copied in; `baseline_json` = deep-copy of `baseline_json or working_json`. | MVP |
| R-05 | `active_version_id` set only if it matches a restored version id; otherwise null. Never 500 on a bad value. | MVP |
| R-06 | `409` if the session already has versions (restore only into an empty session → client retries are safe). `404` if the session is missing. | MVP |
| R-07 | Returns the full session dict (`SessionResponse`) so the frontend hydrates in one step. | MVP |

---

## 4. Contract (OpenAPI-first)

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | `openapi/spec.yaml` edited first: add the `restore` path + `RestoreVersionsRequest` schema + `Error409` response. | MVP |
| C-02 | Add the previously-missing `POST /api/sessions/{sessionId}/versions/select` path (implemented but absent from the spec). | MVP |
| C-03 | Add `RestoreVersionsRequest` Pydantic model to `models.py` mirroring the schema. | MVP |

---

## 5. Data Flow

### 5.1 Restore (happy path)

```
1. Frontend POST /api/sessions/{sid}/versions/restore {versions, working_json, ...}
2. Controller → version_service.restore_versions(sid, req)
3. get_session(sid); 409 if session already has versions
4. session["versions"] = [v.model_dump() for v in req.versions]  (verbatim)
5. working_json / baseline_json / active_version_id applied
6. store.save_session(session)
7. Return full session dict (200)
```

### 5.2 Session Already Has Versions

```
1. POST .../versions/restore into a non-empty session
2. version_service raises ConflictError
3. Controller → 409 {"detail": "Session already has versions"}
```

---

## 6. Excluded from MVP

- A real database implementation of `SessionStore` (interface only for now).
- Per-session or user-scoped auth keys (auth stays a shared dev key).
- Restoring conversation history (only versions + working JSON).
- Concurrency locks around read-modify-write (single-process in-memory).
- TTL / eviction of old sessions.

---

*End of requirements. Feature branch: `cache-store`. Implementation files: `db/session_store.py` (new), `services/` (new), `controllers/` (new), `models.py`, `openapi/spec.yaml`.*
