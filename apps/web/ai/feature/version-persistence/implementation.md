# JSON AI Studio — Version Persistence Frontend Implementation Guide

**Feature branch:** `cache-store`
**Requirements:** `requirements.md`
**ADR:** ADR-0014 (IndexedDB cache + bulk restore)

---

## 1. Architecture

```
Mirror (write):
  state change → debounced 500ms useEffect → saveWorkspace() → IndexedDB 'workspace'/'current'

Restore (load):
  apiKey ready → read localStorage sessionId + loadWorkspace()
    getSession(sessionId) →
      ok        → hydrate from backend
      404       → createSession('Restored') → restoreVersions(newSid, cache) → hydrate
      net/5xx   → error toast, keep cache, retry next reload
```

**Key principle:** the backend is the source of truth while it is alive; IndexedDB is a durable mirror that only takes over when the backend has forgotten the session (404). A single debounced effect owns all writes so no individual callback has to remember to persist.

---

## 2. Component Details

### 2.1 `package.json` — Add `idb` Dependency

**Location:** `apps/web/package.json`
**Action:** Add to `dependencies`, install with `--legacy-peer-deps` (react-diff-viewer does not declare React 19 peer support).

```
npm install idb --legacy-peer-deps
```

### 2.2 `versionCache.ts` — New Module

**Location:** `apps/web/src/lib/versionCache.ts`
**Action:** New file.

```typescript
import { openDB } from 'idb';
const DB_NAME = 'json-ai-studio', DB_VERSION = 1, STORE = 'workspace', KEY = 'current';

export type CachedVersionSnapshot = { id; parent_id; json_data; label; created_at };
export type CachedWorkspace = { sessionId; versions; workingJson; baselineJson; activeVersionId; updatedAt };

export async function saveWorkspace(ws): Promise<void> { /* try/catch → console.warn */ }
export async function loadWorkspace(): Promise<CachedWorkspace | null> { /* returns record or null */ }
export async function clearWorkspace(): Promise<void> { /* delete 'current' */ }
```

Every function bails when `typeof indexedDB === 'undefined'` and wraps access in try/catch → no-op + `console.warn`. Never throws to callers.

### 2.3 `api.ts` — Add `restoreVersions()` + `getSession` Status

**Location:** `apps/web/src/lib/api.ts`
**Action:** Add `restoreVersions`; modify `getSession`.

```typescript
export async function restoreVersions(sessionId, payload, apiKey) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/versions/restore`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to restore versions: ${await res.text()}`);
    return await res.json();
}

// getSession: distinguish 404 (restorable) from network/5xx (retry later)
if (!res.ok) {
    const err: any = new Error(`Failed to load session: ${res.status}`);
    err.status = res.status;
    throw err;
}
```

### 2.4 `SessionContext.tsx` — Restore Flow + Mirror + clearCache

**Location:** `apps/web/src/context/SessionContext.tsx`

**Step 1:** Import cache + `useRef`; extend the version type and `SessionContextValue` (`clearCache`).

```typescript
import { saveWorkspace, loadWorkspace, clearWorkspace } from '../lib/versionCache';
type SessionVersion = { id; label; json_data; parent_id?; created_at? };
```

**Step 2:** `mapVersions(versions)` — map backend versions carrying `parent_id` + `created_at`. Reuse everywhere versions enter state (hydrate, createSession, refreshSession).

**Step 3:** Replace the old hydrate effect with the restore flow, guarded by `restoreStartedRef`:

```typescript
const restoreStartedRef = useRef(false);
useEffect(() => {
    if (!apiKey || restoreStartedRef.current) return;
    restoreStartedRef.current = true;
    const hydrate = async () => {
        // read localStorage sessionId + loadWorkspace()
        // getSession → ok: hydrate | 404: restore | other: toast + keep cache
        // restore: createSession('Restored') → restoreVersions(...) → hydrate + success toast
    };
    hydrate();
}, [apiKey]);
```

**Step 4:** Add the debounced mirror effect:

```typescript
useEffect(() => {
    if (state.loading || !state.sessionId) return;
    const t = setTimeout(() => saveWorkspace({ /* full workspace */ }), 500);
    return () => clearTimeout(t);
}, [state.sessionId, state.versions, state.workingJson, state.baselineJson, state.activeVersionId, state.loading]);
```

**Step 5:** Add `clearCache`:

```typescript
const clearCache = useCallback(async () => {
    await clearWorkspace();
    toast.success('Cached versions cleared from this browser.');
}, []);
```

**Step 6:** Add `clearCache` to the `SessionContext.Provider` value.

### 2.5 `VersionSidebar.tsx` — Clear Button

**Location:** `apps/web/src/components/VersionSidebar.tsx`
**Action:** Add a footer button.

```tsx
import { Trash2 } from 'lucide-react';
const { ..., clearCache } = useSession();
// footer:
<button onClick={() => clearCache()} title="Remove versions cached in this browser (IndexedDB)"
    className="w-full flex items-center justify-center gap-2 px-3 py-1.5 border text-sm rounded-lg text-muted-foreground hover:bg-gray-50">
    <Trash2 className="w-4 h-4" /><span>Clear cached data</span>
</button>
```

---

## 3. Data Flow

### 3.1 Happy Path (backend alive)

```
1. App loads; localStorage sessionId present; backend alive
2. getSession(sessionId) → 200 → hydrate from backend
3. Mirror effect re-syncs IndexedDB (no restore toast)
```

### 3.2 Restore Path (backend restarted)

```
1. getSession(sessionId) → 404
2. createSession('Restored') → newSid
3. restoreVersions(newSid, {versions, working_json, baseline_json, active_version_id})
4. localStorage sessionId = newSid; hydrate; "Restored N version(s) from browser cache." toast
```

### 3.3 Backend Unreachable

```
1. getSession(sessionId) throws with status !== 404
2. "Backend unreachable..." toast; loading=false; localStorage + IndexedDB kept
3. Next reload retries
```

---

## 4. Error Handling

| Scenario | Response |
|----------|----------|
| IndexedDB unavailable (private browsing) | Cache functions no-op + `console.warn`; app works without persistence |
| `getSession` 404 | Fall through to restore |
| `getSession` network/5xx | Error toast; keep cache + localStorage; retry next reload |
| `createSession` / `restoreVersions` fails | Warning toast; keep IndexedDB for retry; empty state |
| StrictMode double-mount | `restoreStartedRef` prevents a second session |

---

## 5. Assumptions & Constraints

1. **Single `'current'` record.** Multi-tab is last-writer-wins (accepted MVP limit).
2. **Versions + working JSON only.** Conversation history is not cached.
3. **New sessionId on restore.** The restored session gets a new id; version snapshots keep their ids.
4. **`idb` dependency.** Installed with `--legacy-peer-deps`.
5. **Debounced writes.** A 500 ms debounce coalesces rapid state changes into one IndexedDB write.
6. **Backend is source of truth.** Cache only takes over on 404, never overrides a live backend session.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/web/package.json` | **MODIFIED** | Add `idb` dependency |
| `apps/web/src/lib/versionCache.ts` | **NEW** | IndexedDB workspace mirror |
| `apps/web/src/lib/api.ts` | **MODIFIED** | Add `restoreVersions()`; `getSession` carries HTTP status on error |
| `apps/web/src/context/SessionContext.tsx` | **MODIFIED** | Restore flow + debounced mirror effect + `clearCache` + `mapVersions` |
| `apps/web/src/components/VersionSidebar.tsx` | **MODIFIED** | "Clear cached data" button |

**No changes to:** `UploadPanel.tsx`, `ChatPanel.tsx`, `JSONTree.tsx`, `DiffViewer.tsx`, `VersionModal.tsx`.

---

## 7. Verification

### Manual Tests

1. **Mirror:** Upload JSON, create 2 versions → DevTools ▸ Application ▸ IndexedDB ▸ `json-ai-studio` ▸ `workspace` ▸ `'current'` populated (debounced).
2. **Normal hydrate:** Reload with backend alive → no restore toast, state loads from backend.
3. **Restore:** Restart uvicorn, reload → "Restored N version(s)" toast; sidebar shows versions; select works; working JSON survived.
4. **Backend down:** Reload with backend stopped → error toast, cache intact; start backend, reload → restore succeeds.
5. **StrictMode:** Dev double-mount creates exactly one backend session (check API logs).
6. **Clear:** Click "Clear cached data" → IndexedDB record removed.
7. **Private browsing:** Firefox private window → app loads and works, only cache disabled.

---

*End of implementation guide. Feature branch: `cache-store`.*
