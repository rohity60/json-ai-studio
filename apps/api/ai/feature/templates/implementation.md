# Backend Implementation Guide — Templates & Knowledge Hub

**Feature branch:** `templates`
**Requirements:** `requirements.md`

The backend addition is intentionally small: one endpoint that seeds a session from static template JSON supplied by the web layer, plus telemetry. Everything else (content, search, blog, SEO) is static in the web repo.

---

## 1. Architecture

```
POST /api/sessions/from-template
  → require_api_key (principal)
  → validate json is object + size <= MAX_TEMPLATE_JSON_BYTES
  → session_service.create_from_template(json, name, starter_prompts)
      → create_session(name)          # existing in-memory path (ADR-0013)
      → session["working_json"] = json
  → log feature="template-open" template_slug=...
  → 201 SessionResponse + starter_prompts
```

**Key principle:** no new store, no new table, no LLM call. Reuse the session lifecycle. The endpoint is a thin controller over `session_service`, matching `controllers/sessions.py`.

---

## 2. Component Details

### 2.1 `openapi/spec.yaml` — Contract First (ADR-0011)

Add the path and schema. Bump the endpoint/schema counts in `CLAUDE.md` afterward.

```yaml
  /api/sessions/from-template:
    post:
      tags: [sessions]
      summary: Seed a new session from a static template
      operationId: seedSessionFromTemplate
      security:
        - ApiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SeedFromTemplateRequest'
      responses:
        '201':
          description: Session created and seeded with template JSON
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SessionResponse'
        '413': { description: Template JSON too large }
        '422': { description: Invalid template payload }
```

```yaml
    SeedFromTemplateRequest:
      type: object
      required: [templateSlug, json]
      properties:
        templateSlug:  { type: string, maxLength: 200 }
        templateTitle: { type: string, nullable: true }
        json:          { type: object, additionalProperties: true }
        starterPrompts:
          type: array
          maxItems: 8
          items: { type: string }
```

Add `starter_prompts` (array of string, default `[]`) to the existing `SessionResponse` schema.

### 2.2 `settings.py` — Size Cap

```python
class Settings(BaseSettings):
    ...
    MAX_TEMPLATE_JSON_BYTES: int = 262144  # 256 KB
```

### 2.3 `models.py` — Pydantic

```python
class SeedFromTemplateRequest(BaseModel):
    templateSlug: str = Field(..., max_length=200)
    templateTitle: str | None = None
    json: dict[str, Any]
    starterPrompts: list[str] = Field(default_factory=list, max_length=8)


# On the session response model used by /api/sessions responses:
class SessionResponse(Session):
    ...
    starter_prompts: list[str] = Field(default_factory=list)
```

> Field names mirror the wire format exactly (`templateSlug`, `json`, `starterPrompts` in; `starter_prompts` out — matching the existing snake_case `working_json` convention on responses).

### 2.4 `services/session_service.py` — Seed Method

```python
async def create_from_template(
    json_doc: dict[str, Any],
    name: str | None = None,
    starter_prompts: list[str] | None = None,
) -> dict[str, Any]:
    """Create a session preloaded with template JSON. Reuses create_session()."""
    session = await create_session(name=name)
    stored = await get_session(session["sessionId"])
    stored["working_json"] = json_doc if isinstance(json_doc, dict) else {}
    # starter_prompts are transient response metadata, not session state
    session["working_json"] = stored["working_json"]
    session["starter_prompts"] = list(starter_prompts or [])
    return session
```

> Follow the actual store API in this file (whether `create_session` returns the live dict or an id — adapt the two-line body accordingly). Do **not** snapshot a version here (T-06).

### 2.5 `controllers/sessions.py` — Endpoint

```python
import json as _json
from ..models import SeedFromTemplateRequest
from ..settings import get_settings


@router.post("/sessions/from-template", status_code=201)
async def endpoint_seed_from_template(
    req: SeedFromTemplateRequest,
    _auth=Depends(require_api_key),
):
    """Seed a new session from a static template (Open in Workspace)."""
    if not isinstance(req.json, dict):
        raise HTTPException(status_code=422, detail="json must be an object")

    size = len(_json.dumps(req.json).encode("utf-8"))
    if size > get_settings().MAX_TEMPLATE_JSON_BYTES:
        raise HTTPException(status_code=413, detail="Template JSON too large")

    logger.info(
        "POST /api/sessions/from-template principal=%s template_slug=%s json_bytes=%d",
        _auth.kind, req.templateSlug, size,
    )

    return await session_service.create_from_template(
        json_doc=req.json,
        name=req.templateTitle or req.templateSlug,
        starter_prompts=req.starterPrompts,
    )
```

---

## 3. Error Handling

| Error | When | Response |
|-------|------|----------|
| `422` | `json` not an object / slug missing / >8 prompts | `{"detail": "..."}` (or Pydantic 422) |
| `413` | serialized `json` > `MAX_TEMPLATE_JSON_BYTES` | `{"detail": "Template JSON too large"}` |
| `401` | invalid API key | `require_api_key` middleware |
| `429` | request rate exceeded | rate limiter |

No `402`/credit errors — seeding makes no LLM call.

---

## 4. Assumptions & Constraints

1. **Content is static in the web repo.** The server never sees the full template catalog; it only receives the JSON of the one template being opened.
2. **Ephemeral session, standard lifecycle.** A template-seeded session is an ordinary session (ADR-0006/0013). The browser's IndexedDB mirror (ADR-0014) picks it up like any other.
3. **Free seeding.** No credit deduction; billing happens on the subsequent chat/explain the user triggers.
4. **starter_prompts are response-only metadata**, not persisted session state — the studio reads them once from the create response.
5. **Trusts client JSON size after the cap check** — the 256 KB limit guards memory; templates are far smaller.

---

## 5. Files Modified

| File | Action | Change |
|------|--------|--------|
| `openapi/spec.yaml` | **MODIFIED** | Add `/api/sessions/from-template` path + `SeedFromTemplateRequest` + `starter_prompts` on `SessionResponse` |
| `apps/api/src/json_ai_studio/settings.py` | **MODIFIED** | Add `MAX_TEMPLATE_JSON_BYTES` |
| `apps/api/src/json_ai_studio/models.py` | **MODIFIED** | Add `SeedFromTemplateRequest`; `starter_prompts` on session response |
| `apps/api/src/json_ai_studio/services/session_service.py` | **MODIFIED** | Add `create_from_template()` |
| `apps/api/src/json_ai_studio/controllers/sessions.py` | **MODIFIED** | Add `POST /api/sessions/from-template` |

**No changes to:** `db/*`, `gateway.py`, `prompting.py`, `utils.py`, workspace/version/diff services.

Run `black .` in `apps/api` after edits.

---

## 6. Verification

### Manual Tests
1. **Happy path:** `curl -X POST :8000/api/sessions/from-template -H 'X-API-Key: dev' -d '{"templateSlug":"aws-iam","json":{"a":1},"starterPrompts":["Explain this"]}'` → `201`, body has `sessionId`, `working_json={"a":1}`, `starter_prompts=["Explain this"]`.
2. **GET back:** `GET /api/sessions/{id}` returns the seeded `working_json`.
3. **Bad shape:** body with `"json": [1,2]` → `422`.
4. **Oversized:** `json` > 256 KB → `413`.
5. **Auth:** missing `X-API-Key` → `401`; hammer to confirm `429`.
6. **Telemetry:** log line `feature="template-open" template_slug=aws-iam` present; no JSON body at INFO.
7. **Swagger:** endpoint appears at `/docs` with the new schema.

---

*End of backend implementation guide. Feature branch: `templates`.*
