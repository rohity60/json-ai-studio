# Version Persistence Feature (Backend) — Task List

**Feature branch:** `cache-store`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Edit `openapi/spec.yaml` first: add `POST .../versions/restore` path, the missing `.../versions/select` path, `RestoreVersionsRequest` schema, and `Error409` response | done |
| 2 | Add `RestoreVersionsRequest` model to `apps/api/src/json_ai_studio/models.py` | done |
| 3 | Create `apps/api/src/json_ai_studio/db/session_store.py` — `SessionStore` ABC + `InMemorySessionStore` + `store` singleton; fix ISO timestamps + `active_version_id`; delete old `store.py` | done |
| 4 | Create `apps/api/src/json_ai_studio/services/errors.py` — `NotFoundError` / `ConflictError` / `InvalidInputError` | done |
| 5 | Create `services/{session,version,chat,diff}_service.py` — move business logic out of `main.py` verbatim; add `version_service.restore_versions` | done |
| 6 | Create `controllers/*.py` — one thin router per resource (health, sessions, versions incl. restore, uploads, chat, diffs, explain); `controllers/__init__.py` exposes `routers` | done |
| 7 | Reduce `main.py` to a thin app factory (FastAPI init, CORS, `include_router` per controller); run `black .` | done |
| 8 | Verify — boot server, smoke-test all endpoints via `:8000/docs`; restore 200 / 409 / 404 / bad-active-id cases | done |

---

*Total: 8 tasks. Sequential: 1→2→3→4→5→6→7→8.*
