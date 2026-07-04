# Version Selection — Frontend Task List

**Feature branch:** `mvp`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `selectVersion(sessionId, versionId, apiKey)` to `apps/web/src/lib/api.ts` — POST to `/api/sessions/{id}/versions/select` | done |
| 2 | Add `activeVersionId: string | null` to `SessionState` type in `SessionContext.tsx` | done |
| 3 | Replace no-op `selectVersion` in `SessionContext.tsx` with async API call + state reset (workingJson, baselineJson, conversationHistory, activeVersionId) | done |
| 4 | Create `apps/web/src/components/UnsavedChangesModal.tsx` — modal with "Save & Continue" and "Continue Without Saving" buttons | done |
| 5 | Add `deepEqual` helper to `SessionContext.tsx` + unsaved-changes detection before calling `selectVersion` | done |
| 6 | Wire `UnsavedChangesModal` into `SessionProvider` render + `handleSaveAndContinue` / `handleDiscardAndContinue` callbacks | done |
| 7 | Update `VersionSidebar` click handler to pass `version.id` string instead of full version object | done |
| 8 | Verify — test no unsaved changes (no modal), with unsaved changes + save, with unsaved changes + discard, save fails (toast + modal stays), select fails (toast + modal stays) | done |

---

*Total: 8 tasks. Sequential: 1→2→3→4→5→6→7→8.*
