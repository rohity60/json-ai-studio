# JSON AI Studio — Version Selection Implementation Guide

**Feature branch:** `mvp`
**Requirements:** `requirements.md`

---

## 1. Architecture

```
POST /api/sessions/{id}/versions/select
    → get_session(sid)
    → find VersionSnapshot by versionId in session["versions"]
    → deep copy version.json_data → working_json + baseline_json
    → set session["active_version_id"] = versionId
    → clear session["conversation_history"]
    → save_session(session)
    → return { working_json, baseline_json, active_version_id, versions, conversation_history: [] }
```

**Key principle:** `select_version()` is a stateful mutation. It deep-copies the selected snapshot into both `working_json` and `baseline_json`, resets conversation history, and saves. The frontend must detect unsaved local changes before calling this endpoint.

---

## 2. Component Details

### 2.1 `main.py` — New Endpoint

**Location:** `apps/api/src/json_ai_studio/main.py`
**Add after line 356 (after `endpoint_create_version_snapshot`)**

```python
@app.post("/api/sessions/{session_id}/versions/select")
async def endpoint_select_version(
    session_id: str,
    req: dict,
    _auth=Depends(require_api_key),
):
    """Select a version snapshot as the new working baseline."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    version_id = req.get("versionId")
    if not version_id:
        raise HTTPException(status_code=400, detail="versionId is required")

    # Find the version in the session's versions list
    versions_list = session.get("versions", [])
    target = None
    for v in versions_list:
        vid = v.id if hasattr(v, "id") else v.get("id")
        if vid == version_id:
            target = v
            break

    if target is None:
        raise HTTPException(status_code=404, detail="Version not found")

    import copy

    # Deep copy the selected version into both working and baseline
    json_data = target.json_data if hasattr(target, "json_data") else target.get("json_data", {})
    session["working_json"] = copy.deepcopy(json_data)
    session["baseline_json"] = copy.deepcopy(json_data)

    # Track active version
    session["active_version_id"] = version_id

    # Reset conversation history
    session["conversation_history"] = []

    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)

    return {
        "working_json": session["working_json"],
        "baseline_json": session["baseline_json"],
        "active_version_id": session["active_version_id"],
        "versions": [v.model_dump() if hasattr(v, "model_dump") else v for v in versions_list],
        "conversation_history": [],
    }
```

### 2.2 `models.py` — Add Request Model

**Location:** `apps/api/src/json_ai_studio/models.py`
**Add after `CreateVersionRequest`**

```python
class SelectVersionRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/versions/select."""
    versionId: str
```

### 2.3 `store.py` — No Changes

The in-memory store already supports all needed operations. `select_version()` uses `get_session()`, mutates the dict in-place, and calls `save_session()`.

### 2.4 `deployment.py` — No Changes

Version selection is orthogonal to deployment registry. No changes needed.

---

## 3. Data Flow

### 3.1 Happy Path

```
1. POST /api/sessions/abc123/versions/select
   Body: { "versionId": "v2" }
2. get_session("abc123") → session dict
3. Find version with id="v2" in session["versions"]
4. json_data = version.json_data (deep copy)
5. session["working_json"] = copy(json_data)
6. session["baseline_json"] = copy(json_data)
7. session["active_version_id"] = "v2"
8. session["conversation_history"] = []
9. save_session(session)
10. Return: {
       "working_json": {...},
       "baseline_json": {...},
       "active_version_id": "v2",
       "versions": [...],
       "conversation_history": []
   }
```

### 3.2 Version Not Found

```
1. POST /api/sessions/abc123/versions/select
   Body: { "versionId": "v99" }
2. No version with id="v99" in session["versions"]
3. Return 404: { "detail": "Version not found" }
```

### 3.3 Session Not Found

```
1. POST /api/sessions/nonexistent/versions/select
   Body: { "versionId": "v2" }
2. get_session("nonexistent") → None
3. Return 404: { "detail": "Session not found" }
```

### 3.4 No-Op (Same Version Selected)

```
1. POST /api/sessions/abc123/versions/select
   Body: { "versionId": "v2" }
2. session["active_version_id"] is already "v2"
3. Still deep-copy and save (idempotent — same result)
4. Return 200 with unchanged state
```

---

## 4. Error Handling

| Error | When | Response |
|-------|------|----------|
| `HTTPException 404` | Session not found | `{ "detail": "Session not found" }` |
| `HTTPException 404` | VersionId not in versions list | `{ "detail": "Version not found" }` |
| `HTTPException 400` | Missing versionId in request body | `{ "detail": "versionId is required" }` |

---

## 5. Assumptions & Constraints

1. **In-memory only.** No database. Session state lost on restart. Matches ADR-0006.
2. **Deep copy required.** `working_json` and `baseline_json` must be independent copies of the version's `json_data`. Mutations to one must not affect the other or the stored snapshot.
3. **Conversation history reset is mandatory.** Selecting a version branches the session; old chat turns are irrelevant to the new branch.
4. **Idempotent.** Selecting the already-active version is a no-op but must still return 200 with the full state.
5. **No auth bypass.** All endpoints protected by `require_api_key` dependency.
6. **Unsaved-changes guard is frontend-only.** Backend always accepts the select request. The frontend must detect if `workingJson !== baselineJson` before calling this endpoint.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/api/src/json_ai_studio/main.py` | **MODIFIED** | Add `endpoint_select_version()` after `endpoint_create_version_snapshot` |
| `apps/api/src/json_ai_studio/models.py` | **MODIFIED** | Add `SelectVersionRequest` model |
| `apps/api/ai/feature/mvp/implementation.md` | **NEW** | This document |

**No changes to:** `store.py`, `deployment.py`, `auth.py`, `utils.py`.

---

## 7. Verification

### Manual Tests

1. **Happy path:** Create a session. Upload JSON. Create version "v1". Modify via chat. Create version "v2". Select "v1". Verify `working_json` and `baseline_json` both equal the "v1" snapshot. Verify `conversation_history` is empty. Verify `active_version_id` is "v1".
2. **Version not found:** Select non-existent versionId. Verify 404 with "Version not found".
3. **Session not found:** Call select on non-existent session ID. Verify 404 with "Session not found".
4. **No-Op:** Select the currently active version. Verify 200 with unchanged state.
5. **Missing versionId:** Send empty body. Verify 400 with "versionId is required".
6. **Deep copy isolation:** Select a version. Modify via chat. Verify the original version snapshot in `versions` list is unchanged.

### Code Review Checklist

- [ ] `endpoint_select_version()` finds version by `versionId` in `session["versions"]`.
- [ ] Deep copies `version.json_data` into both `working_json` and `baseline_json`.
- [ ] Sets `session["active_version_id"]` to the selected versionId.
- [ ] Clears `session["conversation_history"]` to `[]`.
- [ ] Saves session and returns full updated state.
- [ ] Returns 404 for missing session or missing version.
- [ ] Returns 400 for missing versionId.
- [ ] Uses `require_api_key` dependency.
- [ ] `SelectVersionRequest` model added to `models.py`.

---

## 8. Glossary

| Term | Definition |
|------|-----------|
| **Version Selection** | The operation of taking a previously saved `VersionSnapshot` and making it the current `working_json` + `baseline_json`. |
| **Active Version** | The `versionId` stored in `session["active_version_id"]`. The version the user is currently working on. |
| **Deep Copy** | A full recursive copy of a dict/list. Mutations to the copy do not affect the original. |
| **No-Op** | An operation that produces no observable state change. Selecting the already-active version is a no-op. |
| **Branching Point** | Selecting a version creates a new branch in the session's history. Old conversation history is discarded. |

---

*End of implementation guide. Feature branch: `mvp`.*
