# Workspaces Feature (Frontend) — Task List

**Feature branch:** `workspace`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add workspace types + `workspaceHeaders()` (bearer-only, throws 401/loginAvailable) + 11 client functions to `apps/web/src/lib/api.ts` | done |
| 2 | Create `apps/web/src/context/WorkspaceContext.tsx` — provider skeleton: state, `refreshWorkspaces()`, `createWorkspace()`, `renameWorkspace()`, `deleteWorkspace()`, `selectWorkspace()`; active ids persisted to `localStorage['json-ai-studio-workspace']` | done |
| 3 | Add dirty tracking to `WorkspaceContext` — `savedSnapshotRef` + `savedVersionIdsRef` vs `useSession()` workingJson/versions; `markClean()`; `dirty` exposed | done |
| 4 | Create `apps/web/src/components/UnsavedChangesModal.tsx` — promise-based `showUnsavedModal(): Promise<'save'\|'discard'\|'cancel'>`, VersionModal module-store pattern; wire `guardDirty()` in `WorkspaceContext` | done |
| 5 | Add `loadDocument()` to `WorkspaceContext` — `getWorkspaceJson` → new `SessionContext.loadSnapshot()` (fresh session + restore, keep DB ids) → baseline reset | done |
| 6 | Create `apps/web/src/components/SaveDialog.tsx` — `showSaveDialog(): Promise<boolean>`; workspace pick/create, tag input, version summary + "+1 version (unsaved changes)", n/5 counter; add `saveWork()` (new-doc POST vs append POST) to `WorkspaceContext` with 409 inline errors | done |
| 7 | Add `kind: 'login'` to `apps/web/src/components/RateLimitModal.tsx` — "Log in to save your work" with existing login CTA | done |
| 8 | Create `apps/web/src/components/WorkspaceSwitcher.tsx` — dropdown: rows with `document_count/5`, inline rename/delete (hidden for default), "New workspace…"; anonymous → "Default (local)" + login CTA | done |
| 9 | Create `apps/web/src/components/JsonDocumentList.tsx` — tag/version_count/updated_at rows, `n/5` header, delete with confirm, row click → `loadDocument()`; anonymous → login CTA | done |
| 10 | Add `deleteDocument()`/`deleteVersion()` actions + limit-disable states (tooltips at 5/5, 409 toast fallback) across `WorkspaceContext`, `JsonDocumentList`, `SaveDialog` | done |
| 11 | Wire `apps/web/src/app/studio/layout.tsx` — `<WorkspaceProvider>` inside `<SessionProvider>`, mount `UnsavedChangesModal` + `SaveDialog` | done |
| 12 | Wire `apps/web/src/app/studio/page.tsx` — header `WorkspaceSwitcher` + Save button (dirty dot; anon → login modal), sidebar JSONs\|Versions tabs, `guardDirty()` on New Session + upload, `beforeunload` when dirty | done |
| 13 | Verify per implementation §7 — login/default flow, save/load round-trip, guard modal paths, limits, duplicate tag, anonymous gating (no workspace requests), localStorage restore, chat/diff regression | partial — anonymous flows verified in browser (login CTA, switcher, JSONs tab, no workspace requests, no console errors); logged-in flows (save/load round-trip, guard, limits) need an Auth0 login |

---

*Total: 13 tasks. Sequential: 1→2→3→4→5→6→7→8→9→10→11→12→13. Backend tasks 1–12 (see `apps/api/ai/feature/workspaces/tasks.md`) must land first — every task from 5 on hits real endpoints.*
