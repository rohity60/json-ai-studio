# Frontend Requirements — JSON AI Studio Version Persistence Feature

Mirror version snapshots and working JSON into the browser, then rehydrate a fresh backend session from that cache when the old one is gone. Only what the **client / UI layer** must implement.

---

## 1. Browser Cache

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | Persist the workspace in IndexedDB (via the `idb` package). DB `json-ai-studio`, object store `workspace`, single record at key `'current'`. | MVP |
| C-02 | Cache record `CachedWorkspace`: `{ sessionId, versions[], workingJson, baselineJson, activeVersionId, updatedAt }`. Versions carry `parent_id` + `created_at` for full-fidelity restore. | MVP |
| C-03 | `saveWorkspace` / `loadWorkspace` / `clearWorkspace` — every function degrades to a no-op + `console.warn` on failure (private browsing, missing IndexedDB). The cache must never break the app. | MVP |
| C-04 | Single record (not per-version): version ids (`v1`, `v2`, …) collide across sessions; one structured-clone record is atomic and survives sessionId churn. | MVP |

---

## 2. Write Path (mirror)

| # | Requirement | Priority |
|---|-------------|----------|
| W-01 | One debounced (500 ms) `useEffect` in `SessionContext` mirrors state to IndexedDB. Watches `[sessionId, versions, workingJson, baselineJson, activeVersionId]`; skipped while `loading`. | MVP |
| W-02 | The single mirror effect covers version create/select, upload, chat completion, and diff accept/reject — no per-callback wiring. | MVP |
| W-03 | Version state mapping (`mapVersions`) carries `parent_id` + `created_at` (previously only `{id, label, json_data}`). | MVP |

---

## 3. Restore Flow (on app load)

| # | Requirement | Priority |
|---|-------------|----------|
| R-01 | On load: read localStorage sessionId + `loadWorkspace()`. If a sessionId exists, call `api.getSession`. | MVP |
| R-02 | `getSession` success → hydrate from backend (backend = source of truth). | MVP |
| R-03 | `getSession` 404 (session gone after restart) → RESTORE branch. | MVP |
| R-04 | `getSession` network/5xx → error toast, KEEP localStorage + cache for the next reload, do NOT create a session. | MVP |
| R-05 | RESTORE (no sessionId or 404) AND cache has versions or non-empty workingJson → `createSession('Restored')` then `restoreVersions(newSid, {...})`. On success update localStorage, hydrate, success toast. | MVP |
| R-06 | Restore failure → keep IndexedDB (retry next reload), warning toast. | MVP |
| R-07 | `restoreStartedRef` (useRef) guards against React StrictMode double-mount creating two sessions. Worst path = 3 requests (get + create + restore), inside the 10 req/min rate limit. | MVP |
| R-08 | `api.getSession` attaches the HTTP status to the thrown error so 404 is distinguishable from network/5xx. | MVP |

---

## 4. Clear-Cache UI

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | "Clear cached data" button in `VersionSidebar` footer → context `clearCache()` → `clearWorkspace()` + toast. | MVP |
| U-02 | Context exposes `clearCache: () => Promise<void>`. | MVP |

---

## 5. Component Details

### 5.1 `versionCache.ts` — New Module

**Location:** `apps/web/src/lib/versionCache.ts`

Exports `CachedVersionSnapshot`, `CachedWorkspace` types and `saveWorkspace` / `loadWorkspace` / `clearWorkspace`. Bails when `typeof indexedDB === 'undefined'`; all access wrapped in try/catch.

### 5.2 `api.ts` — Add `restoreVersions()` + `getSession` Status

**Location:** `apps/web/src/lib/api.ts`

```typescript
export async function restoreVersions(sessionId, payload, apiKey) { /* POST .../versions/restore */ }
// getSession: on !res.ok, throw an error carrying err.status = res.status
```

### 5.3 `SessionContext.tsx` — Restore Flow + Mirror + clearCache

**Location:** `apps/web/src/context/SessionContext.tsx`

Rework the hydrate effect into the restore flow (section 3), add the debounced mirror effect (section 2), add `clearCache`, and extend the `versions` state type + `mapVersions` to carry `parent_id` + `created_at`.

### 5.4 `VersionSidebar.tsx` — Clear Button

**Location:** `apps/web/src/components/VersionSidebar.tsx`

Add a "Clear cached data" button (Trash2 icon) in the footer calling `clearCache()`.

---

## 6. Data Flow

### 6.1 Mirror

```
1. User uploads JSON / creates a version / chats / accepts a diff
2. State changes → debounced (500ms) effect fires
3. saveWorkspace({sessionId, versions, workingJson, baselineJson, activeVersionId, updatedAt})
4. Record written to IndexedDB 'workspace'/'current'
```

### 6.2 Restore After Backend Restart

```
1. App loads; localStorage has sessionId, IndexedDB has workspace
2. api.getSession(sessionId) → 404 (backend restarted)
3. createSession('Restored') → newSid
4. restoreVersions(newSid, {versions, working_json, baseline_json, active_version_id})
5. localStorage sessionId = newSid; hydrate state; "Restored N version(s)" toast
```

### 6.3 Backend Unreachable

```
1. api.getSession(sessionId) throws with status !== 404
2. Error toast; loading=false; localStorage + IndexedDB kept
3. Next reload retries
```

---

## 7. Excluded from MVP

- Caching conversation history (only versions + working JSON).
- Multi-tab conflict resolution (single `'current'` record = last-writer-wins).
- Cache versioning / migration across schema changes.
- Selective per-version restore (all-or-nothing bulk restore).
- Encryption of cached data.

---

*End of requirements. Feature branch: `cache-store`. Depends on backend `POST /api/sessions/{id}/versions/restore`.*
