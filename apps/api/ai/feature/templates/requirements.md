# Backend Requirements — AI Configuration Templates & Knowledge Hub

Derived from PRD `docs/prd/templates.prd`. Only what the **server / API layer** must implement.

**Scope decision:** Template + blog **content lives as static files in the web repo** (git, SSG). The backend does **not** store, list, or search templates. The only backend surface is a **session-seeding endpoint** so "Open in Workspace" starts a real session preloaded with the template JSON + starter prompts, plus telemetry for the "workspace opens from template" success metric.

Feature branch: `templates`.

---

## 1. New Endpoint — Seed Session From Template

| # | Requirement | Priority |
|---|-------------|----------|
| T-01 | `POST /api/sessions/from-template` — creates a new session whose `working_json` is the supplied template JSON. Returns the same shape as `POST /api/sessions` (`SessionResponse`). | MVP |
| T-02 | Request body (`SeedFromTemplateRequest`): `{ "templateSlug": string, "templateTitle": string (optional), "json": object, "starterPrompts": string[] (optional, max 8) }`. | MVP |
| T-03 | Auth: same as every session endpoint — `Depends(require_api_key)` (anonymous `X-API-Key` or Auth0 bearer). Counts toward the caller's request rate limit, **not** the credit pool (no LLM call). | MVP |
| T-04 | Validation: `json` must be a JSON object (`dict`). `templateSlug` required, non-empty, `<= 200` chars. Reject arrays/primitives with `422`. Oversized payloads (`json` serialized `> MAX_TEMPLATE_JSON_BYTES`, default 256 KB) → `413`. | MVP |
| T-05 | Response `201` with `SessionResponse`: `{ sessionId, name, working_json, versions: [], ... }`. `name` defaults to `templateTitle` when provided, else `templateSlug`. | MVP |
| T-06 | The seeded JSON becomes the working baseline. No version snapshot is auto-created (client may snapshot later, same as upload flow). | MVP |
| T-07 | `starterPrompts` are **echoed back** in the response under `starter_prompts` so the studio can render them as chat chips. Server does not execute them. | MVP |
| T-08 | Telemetry: log one structured line `feature="template-open"` with `template_slug`, `principal.kind`, `json_bytes`. Powers the "workspace opens from template" metric. No PII, no JSON body logged at INFO. | MVP |

### Request / Response Schema

```json
// POST /api/sessions/from-template
// Headers: X-API-Key: <key>   (or Authorization: Bearer <token>)
// Body:
{
  "templateSlug": "aws-iam-readonly-policy",
  "templateTitle": "AWS IAM Read-only Policy",
  "json": { "Version": "2012-10-17", "Statement": [ ... ] },
  "starterPrompts": [
    "Explain each statement",
    "Restrict this to one region",
    "Remove unnecessary permissions"
  ]
}

// Response 201 (application/json)
{
  "sessionId": "9f2c...",
  "name": "AWS IAM Read-only Policy",
  "working_json": { "Version": "2012-10-17", "Statement": [ ... ] },
  "versions": [],
  "starter_prompts": [
    "Explain each statement",
    "Restrict this to one region",
    "Remove unnecessary permissions"
  ]
}
```

---

## 2. Contract & Models

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | Add `POST /api/sessions/from-template` to `openapi/spec.yaml` **first** (OpenAPI-first, ADR-0011). New schema `SeedFromTemplateRequest`. Extend `SessionResponse` (or a new `TemplateSessionResponse`) with optional `starter_prompts: string[]`. | MVP |
| C-02 | Add matching Pydantic models to `models.py`: `SeedFromTemplateRequest`, and `starter_prompts: list[str] = []` on the session response model. Field names verbatim from spec. | MVP |
| C-03 | New setting `MAX_TEMPLATE_JSON_BYTES` (default `262144`) as a `Settings` field (pydantic-settings — no manual `os.environ`). | MVP |

---

## 3. Service Layer

| # | Requirement | Priority |
|---|-------------|----------|
| S-01 | `session_service.create_from_template(json_doc, name, starter_prompts)` — reuses `create_session()` then sets `working_json`. No new store; in-memory `SessionStore` unchanged (ADR-0013). | MVP |
| S-02 | Business-rule validation on the seeded JSON is **not** enforced here (templates ship valid); the existing `validate_document()` is only used by the diff/chat path. Do not block seeding on V-04 rules. | MVP |
| S-03 | Controller stays thin: parse request → validate size/shape → call `session_service` → map `ValueError`/domain errors to `422`/`413`. Pattern mirrors `controllers/sessions.py` and `controllers/explain.py`. | MVP |

---

## 4. Data Flow

### 4.1 Happy Path
```
1. Web "Open in Workspace" → POST /api/sessions/from-template {templateSlug, json, starterPrompts}
2. require_api_key resolves principal (anonymous key or bearer)
3. Validate json is object + within size limit
4. session_service.create_from_template() → new session, working_json = json
5. Log feature="template-open" template_slug=...
6. Return 201 SessionResponse + starter_prompts
7. Web redirects to /studio?session=<sessionId>, renders starter prompt chips
```

### 4.2 Bad Payload
```
1. json is an array / primitive, or slug missing
2. Controller raises HTTPException(422)
```

### 4.3 Oversized
```
1. Serialized json > MAX_TEMPLATE_JSON_BYTES
2. Controller raises HTTPException(413)
```

---

## 5. Blog CMS — Backend Impact

Blog is **entirely static/front-end** (MDX in the web repo). The only backend touchpoint is the same `POST /api/sessions/from-template` endpoint, reused by "Open in Workspace" buttons embedded in blog articles. **No blog-specific backend work.**

---

## 6. Excluded from MVP (backend)

- Templates table / `GET /api/templates` list/detail API (content is static in git).
- Server-side template search or filtering (client-side over a build-time index).
- Popularity counters / "used by X developers" (would need a persisted counter table — Phase 3).
- Community-submitted templates, ratings, comments (Phase 3).
- AI-generated templates from natural language.
- Rendering template docs/markdown server-side.
- Per-template credit accounting (seeding is free; the subsequent chat/explain calls bill normally).

---

*End of backend requirements. Feature branch: `templates`. Files touched: `openapi/spec.yaml`, `models.py`, `settings.py`, `services/session_service.py`, `controllers/sessions.py`.*
