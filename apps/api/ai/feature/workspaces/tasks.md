# Workspaces Feature (Backend) — Task List

**Feature branch:** `workspace`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `workspace_max_jsons: int = 5` and `json_max_versions: int = 5` to `apps/api/src/json_ai_studio/settings.py` | done |
| 2 | Add `Workspace`, `JsonDocument`, `JsonVersion` ORM models to `apps/api/src/json_ai_studio/db/models_orm.py` — UNIQUE (user_id, name), UNIQUE (workspace_id, tag), UNIQUE (document_id, version_number), partial unique index on (user_id) WHERE is_default, all FKs ON DELETE CASCADE; no separate FK indexes (composite uniques cover them, ADR-0018 Indexing) | done |
| 3 | Generate + apply Alembic migration `0002` (`uv run alembic revision --autogenerate -m "create workspaces tables"`, verify partial index survived, `uv run alembic upgrade head`) | done |
| 4 | Add 11 workspace paths + 9 schemas to `openapi/spec.yaml` (snake_case wire, operationIds per implementation §2.4) | done |
| 5 | Add Pydantic wire schemas to `apps/api/src/json_ai_studio/models.py` mirroring spec.yaml verbatim | done |
| 6 | Add `LimitExceededError` and `DuplicateError` (ConflictError subclasses with `.detail` dicts) to `apps/api/src/json_ai_studio/services/errors.py` | done |
| 7 | Create `apps/api/src/json_ai_studio/services/workspace_service.py` — workspace CRUD: `ensure_default_workspace`, `list_workspaces`, `create_workspace`, `rename_workspace`, `delete_workspace` (default → ConflictError) | done |
| 8 | Extend `workspace_service.py` with document ops: `list_documents`, `save_document` (single transaction, doc-limit + tag checks), `get_document`, `rename_document`, `delete_document` | done |
| 9 | Extend `workspace_service.py` with version ops: `append_versions` (FOR UPDATE lock, `last_version_number` high-water-mark numbering, version-limit check), `delete_version` (last version → ConflictError) | done |
| 10 | Call `workspace_service.ensure_default_workspace(user.id)` at the end of `upsert_from_claims()` in `services/user_service.py` | done |
| 11 | Create `apps/api/src/json_ai_studio/controllers/workspaces.py` — 11 endpoints, `_require_user` (401 + login_available), domain-error → HTTP mapping; register in `controllers/__init__.py` `routers` list | done |
| 12 | Format (`black .`) + verify per implementation §7: provisioning idempotency, limits (409s), duplicate tag, cross-user 404, anonymous 401, no-DB 503, cascade delete | done |

---

*Total: 12 tasks. Sequential: 1→2→3→4→5→6→7→8→9→10→11→12. Tasks 4–5 (contract) can run in parallel with 2–3 (schema).*
