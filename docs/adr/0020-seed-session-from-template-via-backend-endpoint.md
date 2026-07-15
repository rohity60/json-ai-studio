# 0020-seed-session-from-template-via-backend-endpoint

**Date**: 2026-07-15
**Status**: Accepted

## Context

"Open in AI Workspace" is the conversion action of the Templates & Knowledge Hub (ADR-0019): a visitor on a static template page (or a blog embed) clicks it and lands in `/studio` with that template's JSON already loaded and starter prompts ready. Template JSON is static and lives in the web repo (ADR-0019), so the *content* is available client-side.

Question: how does the static page hand that JSON to the studio and start a working session?

- **Client-side preload** — pass JSON via query string / `localStorage`, let the studio create a session and upload it in the browser.
- **Backend seeding endpoint** — POST the template JSON to the API, which creates a session and returns its id.

## Decision

**A new backend endpoint `POST /api/sessions/from-template` creates a session seeded with the supplied template JSON and echoes back the starter prompts.** The web page calls it, then routes to `/studio?session=<id>`, which hydrates that session (reusing the existing `GET /api/sessions/{id}` path).

```
POST /api/sessions/from-template
  body: { templateSlug, templateTitle?, json, starterPrompts[]? }
  → require_api_key (anonymous X-API-Key or Auth0 bearer)
  → validate json is object + size <= MAX_TEMPLATE_JSON_BYTES (256 KB)
  → session_service.create_from_template()   # reuses create_session(); no new store
  → log feature="template-open" template_slug=…   # conversion telemetry
  → 201 SessionResponse + starter_prompts
```

### Key rules

- **Reuses the session runtime.** No new store, no new table — a template-seeded session is an ordinary in-memory session (ADR-0006/0013) and is mirrored to IndexedDB (ADR-0014) like any other.
- **Free.** No LLM call, so no credit deduction; it counts only toward the request rate limit. Billing happens on the chat/explain the user triggers next.
- **Anonymous-friendly.** The browser `X-API-Key` is sufficient (ADR-0015) — no login gate on opening a template.
- **Server owns the id + telemetry.** The endpoint is the natural, honest place to record the "workspace opens from template" success metric (PRD §2). `starter_prompts` are response-only metadata, not persisted session state.
- **Contract-first.** Path + `SeedFromTemplateRequest` schema land in `openapi/spec.yaml`, then `models.py`, then the hand-written TS client (ADR-0011/0012).
- **Guards.** Non-object `json` → 422; serialized JSON over `MAX_TEMPLATE_JSON_BYTES` → 413.

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Client-side preload (query param / localStorage) | Query strings can't carry large JSON and would leak content into URLs/history (privacy); localStorage handoff is brittle across tabs/navigations. No server-side conversion telemetry — the exact metric this feature is measured on. Would also duplicate session-create + upload orchestration in the browser. |
| Template-lookup endpoint (`POST /api/sessions/from-template/{slug}`, server reads catalog) | Contradicts ADR-0019 — the server has no template catalog; content is static in the web repo. The client already holds the JSON, so it passes it in. |
| Reuse `POST /api/sessions` then `POST /api/json/upload` (two calls) | Two round-trips and no template provenance for telemetry; a single purpose-built endpoint is cleaner and records `template_slug` in one place. |

## Consequences

- **The good:** One small, honest endpoint; large JSON travels safely in the body; server-side conversion metric; anonymous works; session/chat/diff runtime untouched.
- **The bad:** A network hop before the studio opens (vs a purely local handoff) — trivial, and it's the same call that returns the session id the studio needs anyway. Trusts client-supplied JSON up to the size cap (acceptable — templates are small and public).
- **Neutral:** `openapi/spec.yaml` grows one endpoint + one schema, and `SessionResponse` gains optional `starter_prompts` — the endpoint/schema counts in `CLAUDE.md` need bumping. New Settings knob `MAX_TEMPLATE_JSON_BYTES`.
- The studio must hydrate from `?session=` using a dedicated flag, **not** the global `loading` flag (which unmounts the provider and wipes page state — a known trap).

## References

- PRD: `docs/prd/templates.prd` (§2 Goals/metrics, §6 AI Workspace Integration)
- Feature docs: `apps/api/ai/feature/templates/{requirements,implementation}.md`, `apps/web/ai/feature/templates/implementation.md`
- Related: ADR-0019 (static content — why the client holds the JSON), ADR-0006/0013 (session store reused), ADR-0014 (IndexedDB mirror), ADR-0015 (auth/quota), ADR-0011/0012 (contract-first)
