# JSON AI Studio — Version Persistence Backend Implementation Guide

**Feature branch:** `cache-store`
**Requirements:** `requirements.md`
**ADRs:** ADR-0013 (layered backend + SessionStore ABC), ADR-0014 (IndexedDB cache + bulk restore)

---

## 1. Architecture

```
POST /api/sessions/{id}/versions/restore
  → controllers/versions.py: endpoint_restore_versions
    → version_service.restore_versions(session_id, req)
      → store.get_session(id)            # NotFoundError → 404
      → 409 if session["versions"]       # ConflictError
      → session["versions"] = [v.model_dump() for v in req.versions]
      → apply working_json / baseline_json / active_version_id
      → store.save_session(session)
  → Return full session dict (SessionResponse)
```

**Key principle:** three layers with a single responsibility each. Controllers speak HTTP, services speak business logic and are the only layer that touches the store, `db/` owns persistence behind an interface. Swapping the in-memory store for a database is a new class plus a one-line change to the singleton — no endpoint or service edits.

---

## 2. Component Details

### 2.1 `db/session_store.py` — SessionStore ABC + In-Memory Impl

**Location:** `apps/api/src/json_ai_studio/db/session_store.py`
**Action:** New file. Delete the old `store.py`.

```python
class SessionStore(ABC):
    @abstractmethod
    async def create_session(self, *, name: str | None = None) -> dict[str, Any]: ...
    @abstractmethod
    async def get_session(self, session_id: str) -> dict[str, Any] | None: ...
    @abstractmethod
    async def save_session(self, session: dict[str, Any]) -> None: ...
    @abstractmethod
    async def list_sessions(self) -> list[str]: ...
    @abstractmethod
    async def delete_session(self, session_id: str) -> bool: ...

class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
    # ... trivial async bodies; create_session sets ISO timestamps + active_version_id: None

store: SessionStore = InMemorySessionStore()   # module singleton
def get_store() -> SessionStore:               # swap point for a DB impl
    return store
```

**Call-site discipline:** get → mutate → save. The in-memory store returns live references (save is technically redundant), but a DB store returns detached copies — skipping `save_session` would silently drop writes there. Documented in the module docstring.

### 2.2 `services/errors.py` — Domain Exceptions

**Location:** `apps/api/src/json_ai_studio/services/errors.py`
**Action:** New file.

```python
class NotFoundError(Exception): ...       # → 404
class ConflictError(Exception): ...        # → 409
class InvalidInputError(Exception): ...    # → 400
```

Services raise these; controllers map them to `HTTPException`. Services stay transport-agnostic.

### 2.3 `services/` — Business Logic

**Location:** `apps/api/src/json_ai_studio/services/`
**Action:** New files, logic moved out of the old `main.py` verbatim.

- `session_service.py` — `create_session`, `get_session` (raises `NotFoundError`), `upload_json` (parse, strip metadata, set working + baseline). `now_iso()` helper.
- `version_service.py` — `create_snapshot` (`v{n}` ids + parent chain), `select_version` (deep-copy semantics, clears conversation), `list_versions`, `restore_versions` (below).
- `chat_service.py` — SSE helpers (`sse`, `parse_sse`), `_stream_llm`, `chat_event_stream` (persists merged working_json).
- `diff_service.py` — `_find_diff_in_history`, `accept_all` / `reject_all` / `accept_one` / `reject_one`.

`restore_versions`:

```python
async def restore_versions(session_id, req):
    session = await get_session(session_id)              # NotFoundError → 404
    if session.get("versions"):
        raise ConflictError("Session already has versions")  # → 409
    session["versions"] = [v.model_dump(mode="json") for v in req.versions]
    if req.working_json is not None:
        session["working_json"] = deepcopy(req.working_json)
        session["baseline_json"] = deepcopy(req.baseline_json or req.working_json)
    restored_ids = {v.id for v in req.versions}
    session["active_version_id"] = (
        req.active_version_id if req.active_version_id in restored_ids else None
    )
    session["updated_at"] = now_iso()
    await store.save_session(session)
    return session
```

### 2.4 `controllers/` — Thin Routers

**Location:** `apps/api/src/json_ai_studio/controllers/`
**Action:** New files. One router per resource; `controllers/__init__.py` exposes a `routers` list.

`controllers/versions.py` restore handler:

```python
@router.post("/sessions/{session_id}/versions/restore")
async def endpoint_restore_versions(session_id, req: RestoreVersionsRequest, _auth=Depends(require_api_key)):
    try:
        return await version_service.restore_versions(session_id, req)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
```

### 2.5 `main.py` — Thin App Factory

**Location:** `apps/api/src/json_ai_studio/main.py`
**Action:** Replace the ~670-line file.

```python
from .controllers import routers
app = FastAPI(title="JSON AI Studio API", version="0.1.0")
app.add_middleware(CORSMiddleware, ...)
for router in routers:
    app.include_router(router)
```

### 2.6 `models.py` — RestoreVersionsRequest

**Location:** `apps/api/src/json_ai_studio/models.py`
**Action:** Append.

```python
class RestoreVersionsRequest(BaseModel):
    versions: list[VersionSnapshot]
    working_json: dict[str, Any] | None = None
    baseline_json: dict[str, Any] | None = None
    active_version_id: str | None = None
```

### 2.7 `openapi/spec.yaml` — Contract (edit first)

Add the `restore` path (200 → `SessionResponse`, 400/401/404/409/429), the missing `select` path, the `RestoreVersionsRequest` schema, and the `Error409` response.

---

## 3. Data Flow

### 3.1 Happy Path

```
1. POST /api/sessions/{sid}/versions/restore {versions:[v1,v2], working_json:{...}, active_version_id:"v2"}
2. version_service.restore_versions: get_session(sid), versions empty → proceed
3. session["versions"] = [v1, v2] verbatim (ids/labels/created_at preserved)
4. working_json + baseline_json deep-copied; active_version_id = "v2"
5. store.save_session; return full session dict (200)
```

### 3.2 Non-Empty Session

```
1. POST .../restore into a session that already has versions
2. ConflictError → 409 {"detail": "Session already has versions"}
```

### 3.3 Missing Session

```
1. POST .../restore with an unknown session id
2. NotFoundError → 404 {"detail": "Session not found"}
```

---

## 4. Error Handling

| Error | When | Response |
|-------|------|----------|
| `400` | Invalid upload/body payload | `{"detail": "Invalid JSON in upload body"}` |
| `404` | Session (or version) not found | `{"detail": "Session not found"}` |
| `409` | Restore into a session with versions | `{"detail": "Session already has versions"}` |
| `401` | Invalid API key | Handled by `require_api_key` |
| `429` | Rate limit exceeded | Handled by rate limiter |

---

## 5. Assumptions & Constraints

1. **Interface only.** Only `InMemorySessionStore` exists; a DB impl is future work.
2. **Async ABC.** The in-memory bodies are synchronous under the hood at zero cost; async future-proofs the interface.
3. **Sessions-only granularity.** Versions stay embedded; no separate version store.
4. **Verbatim restore.** Snapshot ids/labels/parent chains/timestamps are preserved so the browser cache round-trips losslessly.
5. **409 keeps retries safe.** Restore only into an empty session; a client can retry without duplicating versions.
6. **Behavior preserved.** All existing endpoint response shapes are unchanged.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/api/src/json_ai_studio/db/session_store.py` | **NEW** | `SessionStore` ABC + `InMemorySessionStore` + singleton |
| `apps/api/src/json_ai_studio/services/errors.py` | **NEW** | Domain exceptions |
| `apps/api/src/json_ai_studio/services/{session,version,chat,diff}_service.py` | **NEW** | Business logic moved from `main.py` |
| `apps/api/src/json_ai_studio/controllers/*.py` | **NEW** | One thin router per resource |
| `apps/api/src/json_ai_studio/main.py` | **MODIFIED** | Reduced to a ~40-line app factory |
| `apps/api/src/json_ai_studio/models.py` | **MODIFIED** | Add `RestoreVersionsRequest` |
| `apps/api/src/json_ai_studio/store.py` | **DELETED** | Replaced by `db/session_store.py` |
| `openapi/spec.yaml` | **MODIFIED** | Add restore + select paths, `RestoreVersionsRequest`, `Error409` |

**No changes to:** `auth.py`, `utils.py`, `deployment.py`, `logging_config.py`.

---

## 7. Verification

### Manual Tests

1. **Boot:** Server starts; all pre-existing endpoints respond identically (create/get session, upload, versions create/select/list, diffs, chat SSE, explain).
2. **Timestamps:** New session has real ISO `created_at` / `updated_at` and `active_version_id: null`.
3. **Restore happy path:** Restore 2 snapshots into a fresh session → 200; ids/labels/created_at preserved; working/baseline set.
4. **Conflict:** Restore again into the same session → 409.
5. **Missing session:** Restore into an unknown id → 404.
6. **Bad active id:** Restore with an `active_version_id` not among the versions → nulled, not 500.

---

*End of implementation guide. Feature branch: `cache-store`.*
