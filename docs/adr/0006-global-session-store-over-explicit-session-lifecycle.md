# 0006-global-session-store-over-explicit-session-lifecycle-for-in-memory-storage

**Date**: 2026-06-21
**Status**: Accepted

## Context

For MVP, all sessions live in memory — no external database. We need to decide how the frontend interacts with this storage model: a single global `SessionStore` with auto-generated UUIDs vs. an explicit lifecycle with a dedicated session creation endpoint + store pattern.

## Decision

Use a **Single Global SessionStore with Auto-Generated UUIDs**.

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **Single global `SessionStore` with auto-generated UUIDs** | Simplest URL-based routing. One entry point to start a session (`POST /api/sessions`). Easy to debug via session IDs in URLs/logs. No extra hop to start — client gets ID immediately from upload or chat. | No dedup/checking on duplicate creations unless we add it. Session lifecycle is implicit (no "close" endpoint). | Chosen — MVP simplicity over explicit lifecycle management that adds API surface area without much benefit for a single-user tool. |
| **Dedicated session creation endpoint + store** | Explicit lifecycle: create → use → export. Clear version snapshots at creation time. Easier to reason about state machine from frontend perspective. | One extra hop to start a session (POST /api/sessions) before any chat/diff work. Adds API surface for MVP complexity budget. More routes to document and maintain. | Not chosen — the extra round trip adds latency with no real gain for MVP's in-memory model. |

### Implementation Pattern

```python
class SessionStore:
    _sessions: dict[str, Session] = {}      # id → Session

     @classmethod
    def create(cls) -> str:                 # returns session ID
        sid = uuid4().hex
         cls._sessions[sid] = Session(id=sid, name="Untitled")
        return sid

     @classmethod
    def get(cls, session_id: str) -> Session | None:
        return cls._sessions.get(session_id)

     @classmethod
    def save(cls, session: Session):
         cls._sessions[session.id] = session
```

- No TTL — sessions persist until server restart.
- No persistence layer for MVP (sessions are in-memory only).
- Frontend stores session ID in `localStorage` for survival across refreshes.

## Consequences

### The good
- Simplest possible API contract: `POST /api/sessions` creates + returns `{ id: "..." }` in one response.
- All subsequent operations reference the session via URL path (`/api/sessions/{id}/...`).
- Easy to add persistence later — just wrap `_sessions` in a class that serializes to disk.

### The bad
- No explicit "close" endpoint — sessions live until server restart (acceptable for MVP).
- Memory leaks possible if many concurrent sessions are created without cleanup (unlikely at MVP scale).
- No dedup check on duplicate creations by default.

## References

- Related ADR: [#0007](0007-fail-fast-error-handling-over-retry-pattern.md) (how we handle missing session errors — 404 with retry hint)
