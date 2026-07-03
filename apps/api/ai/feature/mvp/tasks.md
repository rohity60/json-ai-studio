# Version Selection — Task List

**Feature branch:** `mvp`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `SelectVersionRequest` model to `apps/api/src/json_ai_studio/models.py` — `versionId: str` field | done |
| 2 | Add `endpoint_select_version()` to `apps/api/src/json_ai_studio/main.py` — find version, deep copy into working+baseline, reset history, save, return full state | done |
| 3 | Verify — test happy path (select existing version), 404 (version not found), 404 (session not found), 400 (missing versionId), no-op (same version) | done |

---

*Total: 3 tasks. Sequential: 1→2→3.*
