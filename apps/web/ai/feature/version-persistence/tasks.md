# Version Persistence Feature (Frontend) — Task List

**Feature branch:** `cache-store`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `idb` to `apps/web/package.json`; install with `npm install idb --legacy-peer-deps` | done |
| 2 | Create `apps/web/src/lib/versionCache.ts` — IndexedDB workspace mirror (`saveWorkspace` / `loadWorkspace` / `clearWorkspace`), single `'current'` record, no-op on failure | done |
| 3 | Add `restoreVersions()` to `apps/web/src/lib/api.ts`; make `getSession` attach `err.status` on error | done |
| 4 | `SessionContext.tsx` — extend version type + `mapVersions` to carry `parent_id` + `created_at` | done |
| 5 | `SessionContext.tsx` — rework hydrate effect into the restore flow (getSession → 404 → createSession + restoreVersions), guarded by `restoreStartedRef` | done |
| 6 | `SessionContext.tsx` — add debounced (500ms) mirror effect writing the workspace to IndexedDB | done |
| 7 | `SessionContext.tsx` — add `clearCache()` and expose it on the provider value | done |
| 8 | `VersionSidebar.tsx` — add "Clear cached data" button calling `clearCache()` | done |
| 9 | Verify — `tsc --noEmit`; upload + versions populate IndexedDB; restart backend → restore toast; clear button empties the record | done |

---

*Total: 9 tasks. Sequential: 1→2→3→4→5→6→7→8→9.*
