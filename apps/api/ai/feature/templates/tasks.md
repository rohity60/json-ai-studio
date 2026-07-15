# Templates Feature (Backend) — Task List

**Feature branch:** `templates`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

**Status: ✅ implemented & verified 2026-07-15** — `POST /api/sessions/from-template`
live: spec + `SeedFromTemplateRequest` model + `MAX_TEMPLATE_JSON_BYTES` setting +
`session_service.create_from_template()` + controller. `black` clean. TestClient checks
pass (201 happy / 200 get-back / 422 bad shape / 413 oversized) and confirmed live from
the web app. CLAUDE.md counts bumped to 26 endpoints / 33 schemas.

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `POST /api/sessions/from-template` path + `SeedFromTemplateRequest` schema + `starter_prompts` on `SessionResponse` to `openapi/spec.yaml` (contract-first). | pending |
| 2 | Add `MAX_TEMPLATE_JSON_BYTES` (default 262144) as a `Settings` field in `settings.py`. | pending |
| 3 | Add `SeedFromTemplateRequest` Pydantic model + `starter_prompts: list[str]` on the session response model in `models.py`. | pending |
| 4 | Add `session_service.create_from_template(json_doc, name, starter_prompts)` — reuses `create_session()`, sets `working_json`, echoes `starter_prompts`. No version snapshot. | pending |
| 5 | Add `POST /api/sessions/from-template` endpoint to `controllers/sessions.py` — validate object shape (422) + size (413), log `feature="template-open"`, call service, return 201. | pending |
| 6 | `black .` in `apps/api`; update endpoint/schema counts in `CLAUDE.md`. | pending |
| 7 | Verify — curl happy path, GET-back, 422 (array), 413 (oversized), 401/429 auth, Swagger `/docs`. | pending |

---

*Total: 7 tasks. Sequential: 1→2→3→4→5→6→7. Small backend surface — the bulk of this feature is frontend (`apps/web/ai/feature/templates`).*
