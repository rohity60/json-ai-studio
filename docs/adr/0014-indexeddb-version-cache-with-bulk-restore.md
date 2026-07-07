# 0014-indexeddb-version-cache-with-bulk-restore

**Date**: 2026-07-07
**Status**: Accepted

## Context

The backend session store is in-memory (ADR-0006/0013): a server restart loses every session and its version snapshots. The frontend kept only the sessionId in localStorage, so after a restart the user's saved versions were gone for good. We want version snapshots (and unsaved working JSON) to survive backend restarts using browser-side storage, and to rehydrate a fresh backend session from that cache on app load.

## Decision

Mirror the workspace into **IndexedDB** (via the ~1.1 kB `idb` package) as a **single record**, and add a **bulk restore endpoint** `POST /api/sessions/{id}/versions/restore`.

- **Cache shape** (`apps/web/src/lib/versionCache.ts`): DB `json-ai-studio`, object store `workspace`, one record at key `'current'` holding `{sessionId, versions[], workingJson, baselineJson, activeVersionId, updatedAt}`. Single-record because version ids (`v1`, `v2`, …) collide across sessions; one structured-clone record is atomic and survives sessionId churn by design.
- **Write path**: one debounced (500 ms) `useEffect` in `SessionContext` watching `[sessionId, versions, workingJson, baselineJson, activeVersionId]` — covers version create/select, upload, chat completion, and diff accept/reject with no per-callback wiring. Every cache function degrades to a no-op on failure (private browsing, missing IndexedDB) so the cache can never break the app.
- **Restore path** (on app load): if the saved sessionId 404s (backend restarted), create a fresh session and POST the cached snapshots to `.../versions/restore` in one request. The endpoint preserves snapshot ids/labels/parent chains/timestamps verbatim, restores working/baseline JSON, and responds 409 if the session already has versions (restore only into an empty session → client retries are safe). Network/5xx errors do NOT trigger restore — cache and localStorage are kept for the next reload.
- Chat conversation history is **not** cached (product decision — MVP scope).
- A "Clear cached data" button in `VersionSidebar` deletes the record.

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| localStorage | ~5 MB string limit; JSON payloads can exceed it; stringify cost on every mirror write. |
| Loop `POST /versions` per cached version | Burns the 10 req/min rate limit with >7 versions; regenerates ids/timestamps, losing snapshot fidelity. |
| Per-version IndexedDB records | Version ids collide across sessions; multi-record writes are not atomic. |
| Raw IndexedDB API | ~4× the code for the same result; `idb` is 1.1 kB and typed. |
| Caching conversation history too | Out of MVP scope per product decision; adds restore edge cases. |

## Consequences

- Versions and unsaved working JSON survive backend restarts; the restored session gets a new sessionId but identical version snapshots.
- Multi-tab is last-writer-wins on the single `'current'` record (accepted MVP limit).
- Worst-case load path is 3 requests (get + create + restore), inside the 10 req/min rate limit.
