# 0013-layered-backend-and-session-store-abc

**Date**: 2026-07-07
**Status**: Accepted (amends ADR-0006)

## Context

`main.py` had grown to ~670 lines holding all 13 endpoints, SSE streaming, and business logic, and every endpoint called the module-level dict functions in `store.py` directly. Two problems: the file was hard to navigate, and a future database backend would require touching every call site. We need a layered structure and a storage seam that lets a DB implementation slot in without rewriting endpoints.

## Decision

Restructure the backend as **controllers → services → db**, and replace the module-level store functions with an **async `SessionStore` ABC** plus an `InMemorySessionStore` implementation exposed as a module singleton.

```
src/json_ai_studio/
├── main.py            ← thin app factory: FastAPI init, CORS, include_router
├── controllers/       ← APIRouters: parse requests, map domain errors → HTTP codes
├── services/          ← business logic; the only layer that touches the store
│   └── errors.py      ← NotFoundError → 404, ConflictError → 409, InvalidInputError → 400
├── db/
│   └── session_store.py  ← SessionStore ABC + InMemorySessionStore + `store` singleton
└── gateway.py, diff_utils.py, prompting.py, utils.py, ...  ← utils layer (unchanged)
```

Key points:

- **Async interface.** FastAPI endpoints are already `async def`; a DB implementation (asyncpg, async SQLAlchemy) needs async methods. Making the ABC async now avoids a breaking interface change later; the in-memory bodies are trivially synchronous at zero cost.
- **Sessions-only granularity.** Versions stay embedded in the session dict — they are value objects owned by a session, and every API route is session-scoped. A DB implementation can normalize them into a child table behind the same interface.
- **`create_session` returns the full session dict** (not just the id), matching what a DB layer would return and removing an immediate re-read at call sites.
- **get → mutate → save discipline.** The in-memory store returns live references, making `save_session` technically redundant today, but a DB implementation will return detached copies — call sites must keep calling `save_session`.
- Bundled fixes: `created_at`/`updated_at` are now set to real ISO timestamps at creation (previously stuck as `""`), and new sessions include `"active_version_id": None`.

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Sync interface | Would force a breaking change the moment a real DB driver arrives. |
| Separate `VersionStore` alongside `SessionStore` | Doubles the interface surface for no MVP benefit; versions are never accessed outside a session. |
| FastAPI `Depends` injection of the store | Nice-to-have for tests, but the module singleton keeps call sites minimal; can be layered on later without changing the ABC. |
| Keep everything in `main.py` | Rejected by this ADR — the file had become the bottleneck for every change. |

## Consequences

- Endpoint behavior and response shapes are unchanged (verified by smoke tests against all 13 routes).
- A DB-backed store is now a single new class + one-line swap of the `store` singleton.
- Services raise domain exceptions and never `HTTPException`, keeping them transport-agnostic.
