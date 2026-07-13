# JSON AI Studio — Workspaces Feature Implementation Guide (Frontend)

**Feature branch:** `workspace`
**Requirements:** `requirements.md`
**ADR:** `docs/adr/0018-workspaces-as-persistence-layer-over-sessions.md`

---

## 1. Architecture

```
app/studio/layout.tsx
  <SessionProvider>            ← untouched (session runtime)
    <WorkspaceProvider>        ← NEW, nests inside (calls useSession())
      {children}               ← studio/page.tsx
      <Toaster/> <VersionModal/> <RateLimitModal/>
      <UnsavedChangesModal/>   ← NEW (module-level store, VersionModal pattern)
      <SaveDialog/>            ← NEW (module-level store)
```

**Key principles:**
- `WorkspaceContext` owns everything workspace: list, active ids, documents, dirty tracking, save/load. `SessionContext` is not modified.
- Load = `GET .../jsons/{docId}` → map versions into the existing `api.restoreVersions()` payload → latest version becomes working JSON. Save = inverse mapping. The session runtime never knows workspaces exist.
- All workspace API calls are **bearer-only**; anonymous users never reach the network (UI gates with the login popup first).
- Dedicated loading flags everywhere — never touch SessionContext's global `loading` (provider renders `null` while it's true and unmounts page-local state).

---

## 2. Component Details

### 2.1 `lib/api.ts` — Workspace Client + Types

**Action:** Append. Reuse `httpError()` (it already parses `login_available` → `err.loginAvailable`). Workspace calls send bearer only:

```typescript
export type WorkspaceSummary = {
  id: string; name: string; is_default: boolean;
  document_count: number; updated_at: string;
};
export type JsonDocumentSummary = {
  id: string; tag: string; version_count: number;
  latest_version_number: number; updated_at: string;
};
export type WorkspaceJsonVersion = {
  id: string; version_number: number; label: string | null;
  content: Record<string, any>; created_at: string;
};
export type JsonDocumentDetail = { id: string; tag: string; versions: WorkspaceJsonVersion[] };
export type NewVersionPayload = { label: string | null; content: Record<string, any> };

/** Bearer-only headers; workspace routes must never fall back to X-API-Key. */
async function workspaceHeaders(extra: Record<string, string> = {}) {
  const token = await getBearerToken();
  if (!token) {
    const err: any = new Error('Login required');
    err.status = 401; err.loginAvailable = true;
    throw err;
  }
  return { ...extra, Authorization: `Bearer ${token}` };
}
```

Functions (one per route, same fetch/httpError shape as the rest of the file):
`listWorkspaces()`, `createWorkspace(name)`, `renameWorkspace(id, name)`, `deleteWorkspace(id)`, `listWorkspaceJsons(wsId)`, `saveWorkspaceJson(wsId, {tag, versions})`, `getWorkspaceJson(wsId, docId)`, `renameWorkspaceJson(wsId, docId, tag)`, `deleteWorkspaceJson(wsId, docId)`, `appendJsonVersions(wsId, docId, {versions})`, `deleteJsonVersion(wsId, docId, versionId)`.

### 2.2 `context/WorkspaceContext.tsx` — New Provider

**Action:** New file. `'use client'`. Mounted inside `SessionProvider` (needs `useSession()`).

State:

```typescript
type WorkspaceState = {
  workspaces: WorkspaceSummary[];
  activeWorkspaceId: string | null;
  documents: JsonDocumentSummary[];
  activeDocumentId: string | null;
  limits: { maxJsons: number; maxVersions: number };  // constants 5/5 for MVP
  loadingWorkspaces: boolean;
  loadingDocuments: boolean;
  loggedIn: boolean;          // derived from session profile (state.profile != null)
  dirty: boolean;             // see 2.2.1
};
```

Internal refs (not exposed): `savedSnapshotRef: string | null` (JSON.stringify of workingJson at last load/save), `savedVersionIdsRef: Set<string>` (session version ids already persisted).

#### 2.2.1 Dirty tracking

```typescript
const { state: session } = useSession();
const dirty = useMemo(() => {
  if (!loggedIn) return false;                    // anonymous flow never guards
  const unsavedVersions = session.versions.some(v => !savedVersionIdsRef.current.has(v.id));
  const changed = savedSnapshotRef.current !== null
    && JSON.stringify(session.workingJson) !== savedSnapshotRef.current;
  const neverSaved = savedSnapshotRef.current === null
    && Object.keys(session.workingJson).length > 0;
  return unsavedVersions || changed || neverSaved;
}, [session.workingJson, session.versions, loggedIn]);
```

`markClean()` (internal): set `savedSnapshotRef` = stringify(current workingJson), add all persisted version ids to `savedVersionIdsRef`.

#### 2.2.2 Actions

```typescript
refreshWorkspaces()   // GET /workspaces; pick is_default (or localStorage id) as active
createWorkspace(name) // POST; refresh; 409 duplicate → rethrow for inline error
renameWorkspace(id, name); deleteWorkspace(id)
selectWorkspace(id)   // guardDirty() → GET jsons → set documents, clear activeDocumentId
loadDocument(docId)   // guardDirty() → GET doc → hydrate session (see 2.2.3) → markClean()
saveWork(input)       // see 2.2.4
deleteDocument(docId); deleteVersion(docId, versionId)
guardDirty(): Promise<boolean>  // !dirty → true; else showUnsavedModal() promise:
                                //   save → open SaveDialog, resolve true on success
                                //   discard → resolve true; cancel → resolve false
```

`activeWorkspaceId`/`activeDocumentId` persist to `localStorage['json-ai-studio-workspace']` as `{workspaceId, documentId}` (same style as `json-ai-studio-session`); restored in the initial `refreshWorkspaces()` effect.

401 with `loginAvailable` from any action → `showRateLimitModal({scope: 'api', kind: 'login'})` (see 2.7) and revert to anonymous presentation — never clear session state.

#### 2.2.3 Load mapping (workspace → session)

The restore endpoint 409s on a session that already has versions, so load
goes through one new SessionContext method, `loadSnapshot(payload)`: mints a
fresh session, restores into it, hydrates state (same flow as the IndexedDB
boot restore; never touches the global `loading` flag).

```typescript
const doc = await api.getWorkspaceJson(wsId, docId);
const latest = doc.versions[doc.versions.length - 1];
await loadSnapshot({
  versions: doc.versions.map(v => ({
    id: v.id,                    // keep DB ids — savedVersionIds match for free
    parent_id: null,
    json_data: v.content,
    label: v.label ?? `v${v.version_number}`,
    created_at: v.created_at,
  })),
  workingJson: latest.content,   // latest version loads for work
  activeVersionId: latest.id,
});
savedVersionIds = new Set(doc.versions.map(v => v.id));
savedSnapshot = JSON.stringify(latest.content);
```

#### 2.2.4 Save mapping (session → workspace)

```typescript
// Versions not yet persisted, oldest first:
const newVersions = session.versions
  .filter(v => !savedVersionIdsRef.current.has(v.id))
  .map(v => ({ label: v.label, content: v.json_data }));
// Dirty working JSON on top (SaveDialog shows it as "+1 version (unsaved changes)"):
if (workingJsonChanged) newVersions.push({ label: 'Working copy', content: session.workingJson });

if (input.documentId) {
  // Append is deduped by CONTENT against the document's existing versions
  // (canonical key-sorted stringify — JSONB doesn't preserve key order).
  // Reason: the dirty baseline is React state and dies on page reload, and
  // session ids ≠ DB ids for locally created versions, so id bookkeeping
  // alone re-appends duplicates after a reload and burns version slots.
  const existing = await api.getWorkspaceJson(wsId, input.documentId);
  const persisted = new Set(existing.versions.map(v => canonicalJson(v.content)));
  const newOnly = newVersions.filter(v => !persisted.has(canonicalJson(v.content)));
  if (newOnly.length === 0) { markClean(all pending ids); toast.info(...); return; }
  await api.appendJsonVersions(wsId, input.documentId, { versions: newOnly });
} else {
  await api.saveWorkspaceJson(wsId, { tag: input.tag, versions: newVersions }); // ≤5 or 409
}
// markClean(pending session ids); refresh document + workspace lists.
```

### 2.3 `components/UnsavedChangesModal.tsx` — New Component

**Action:** New file. Copy the `VersionModal.tsx` module-level-store pattern exactly:

```typescript
export function showUnsavedModal(): Promise<'save' | 'discard' | 'cancel'>
```

Renders "You have unsaved changes" + three buttons (`ui/Button`). Mounted once in `studio/layout.tsx`. `WorkspaceContext.guardDirty()` awaits it; `'save'` chains into `showSaveDialog()`.

### 2.4 `components/SaveDialog.tsx` — New Component

**Action:** New file, same module-level store pattern: `showSaveDialog(): Promise<boolean>` (true = saved).

1. Workspace `<select>` (from context) + "New workspace" option revealing a name `<input>`.
2. Tag `<input>` — prefilled with active document's tag (append mode) or empty; disabled in append mode.
3. Version summary list: pending version labels + "+1 version (unsaved changes)" row when working JSON is dirty.
4. Counter `will use n/5 version slots`; submit disabled when it exceeds 5 with guidance text.
5. Submit → `saveWork()`; `409 duplicate` → inline field error; `409 limit_exceeded` → dialog-level error with delete guidance; success → sonner toast + resolve(true).

### 2.5 `components/WorkspaceSwitcher.tsx` — New Component

**Action:** New file. Header dropdown (plain button + absolutely-positioned panel, same conventions as existing header controls; lucide-react icons).

- Logged in: rows from `workspaces` (name, `document_count/5`, check on active; pencil = rename inline, trash = delete w/ confirm, hidden for `is_default`), footer "New workspace…" inline input.
- Row click → `selectWorkspace(id)` (guard runs inside).
- Anonymous: single static row **"Default (local)"** + "Log in to create workspaces" button → `showRateLimitModal({scope:'api', kind:'login'})`.

### 2.6 `components/WorkspaceSidebar.tsx` — Unified Tree (replaces JsonDocumentList + VersionSidebar)

**Action:** One sidebar, one tree — documents are parents, versions are their children (they're related data, not two tabs). The JSONs|Versions tab bar is gone; the header shows **workspace details**.

- Header: active workspace name + `n/5 JSONs` (anonymous: "Default (local)" + login hint), refresh, collapse.
- Parent row per document: chevron (expand), tag, `version_count/5`, trash (confirm). Label click → `loadDocument(id)`; active document highlighted + auto-expanded.
- Children of the **active** document = session versions (`state.versions`): active dot, click → `showVersionModal(v)` (unchanged load-version flow).
- Children of **other** documents: lazy-fetched on expand via `api.getWorkspaceJson` (cached per doc); click → `loadDocument(docId)` then `selectVersion(versionId)` (restore keeps DB ids); per-version trash → `deleteVersion`.
- "Current JSON (unsaved)" pseudo-parent when nothing is loaded from a workspace (the whole tree for anonymous users, plus login CTA).
- Footer keeps the session actions verbatim: New Version (inline label input), Export JSON, Clear cached data.

### 2.7 `components/RateLimitModal.tsx` — New `login` Kind

**Action:** Extend the existing modal (it already handles `busy | credits | rate` with a login CTA). Add `kind: 'login'`: title "Log in to save your work", body explains workspaces persist JSONs + versions, primary button = existing login CTA, no retry-after row.

### 2.8 `app/studio/layout.tsx` — Provider Wiring

```tsx
<SessionProvider>
  <WorkspaceProvider>
    {children}
    <Toaster position="top-right" />
    <VersionModal />
    <RateLimitModal />
    <UnsavedChangesModal />
    <SaveDialog />
  </WorkspaceProvider>
</SessionProvider>
```

### 2.9 `app/studio/page.tsx` — Header + Sidebar Wiring

1. Header: `<WorkspaceSwitcher />` left of the sidebar toggle; **Save** button next to "New Session" — anonymous → `showRateLimitModal({kind:'login'})`, logged-in → `showSaveDialog()`. Dot indicator on Save when `dirty`.
2. "New Session" click and Upload flow: `await guardDirty()` before proceeding.
3. Sidebar: render `WorkspaceSidebar` (see 2.6); toolbar toggle button reads "Workspace".
4. `beforeunload` effect: `if (dirty) e.preventDefault()`.

---

## 3. Data Flow

### 3.1 Login lands in default workspace

```
1. Studio mounts → session profile resolves (logged in)
2. WorkspaceContext: refreshWorkspaces() → GET /api/workspaces
3. localStorage workspaceId still exists in list ? that : is_default row → active
4. GET .../jsons → WorkspaceSidebar tree renders; no document auto-loaded
```

### 3.2 Open a document

```
1. Row click → guardDirty() (modal if dirty)
2. GET .../jsons/{docId} → restoreVersions(sessionId, mapped payload)
3. selectVersion(latest) → latest content is working JSON
4. savedVersionIds = doc version ids; markClean(); Versions tab shows them
```

### 3.3 Save

```
1. Save → anonymous? login modal, stop
2. showSaveDialog(): pick/create workspace, tag, version summary
3. New doc → POST .../jsons {tag, versions}; existing → POST .../versions
4. 201 → toast, savedVersionIds updated from response/refetch, markClean()
5. 409 duplicate/limit → inline error, dialog stays open
```

### 3.4 Unsaved-work guard

```
1. Trigger: selectWorkspace / loadDocument / upload / New Session / logout
2. dirty → showUnsavedModal()
   'save'    → showSaveDialog(); saved? continue : stay
   'discard' → continue (session state simply gets replaced)
   'cancel'  → abort the pending action
```

### 3.5 Anonymous flow (unchanged core)

```
1. Upload + createVersion work exactly as today (session + IndexedDB, ADR-0014)
2. Save / 2nd JSON / switcher expansion → login modal (kind:'login')
3. After login: browser still holds the work → user saves via 3.3 (no auto-migration)
```

---

## 4. Error Handling

| Error | When | UI |
|-------|------|----|
| `401` + `loginAvailable` | Token missing/expired on any workspace call | Login modal; workspace UI reverts to anonymous; session state untouched |
| `409 limit_exceeded` | 6th JSON / 6th version | SaveDialog error or toast: "Workspace full — delete a JSON first" / "Version limit reached" |
| `409 duplicate` | Tag/name collision | Inline field error, dialog stays open |
| `404` | Doc/workspace deleted elsewhere | Toast + refresh lists, clear active ids |
| `503` | DB not configured | Toast "Workspaces unavailable"; switcher shows local-only entry |
| Network failure | Any | sonner error toast; state unchanged |

---

## 5. Assumptions & Constraints

1. **SessionContext untouched** — dirty tracking, guards, and mappings live in `WorkspaceContext`.
2. **DB version ids are reused as session version ids** on load (restore preserves ids), so persisted-version bookkeeping is a set intersection, no id mapping table.
3. **Limits hardcoded 5/5 client-side** for counters/disabling; server 409s remain the source of truth (belt-and-braces).
4. **Modal house pattern** — module-level store + `show*()` functions (like `VersionModal`/`RateLimitModal`), no prop drilling, mounted once in studio layout.
5. **Anonymous flow byte-identical to today** — no workspace network calls, IndexedDB mirror (ADR-0014) untouched.
6. **`npm install` needs `--legacy-peer-deps`** in `apps/web` (react-diff-viewer vs React 19) — no new deps expected anyway.
7. **Plain inputs, no form libraries**; sonner toasts; lucide-react icons.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/web/src/lib/api.ts` | **MODIFIED** | +types, +`workspaceHeaders`, +11 client functions |
| `apps/web/src/context/WorkspaceContext.tsx` | **NEW** | Provider: state, dirty tracking, guard, load/save mappings |
| `apps/web/src/components/StatusPill.tsx` | **NEW** (Tier 1) | Header save-status pill: saved / saving / unsaved / local |
| `apps/web/src/components/UnsavedChangesModal.tsx` | **REMOVED** (Tier 1) | Retired — `guardDirty()` auto-saves on switch instead of prompting |
| `apps/web/src/components/SaveDialog.tsx` | **NEW** | Workspace pick/create + tag + version summary |
| `apps/web/src/components/WorkspaceSwitcher.tsx` | **NEW** | Header dropdown |
| `apps/web/src/components/WorkspaceSidebar.tsx` | **NEW** | Unified doc→version tree (JsonDocumentList + VersionSidebar deleted) |
| `apps/web/src/components/RateLimitModal.tsx` | **MODIFIED** | +`kind: 'login'` |
| `apps/web/src/app/studio/layout.tsx` | **MODIFIED** | +WorkspaceProvider, +2 modal mounts |
| `apps/web/src/app/studio/page.tsx` | **MODIFIED** | Action-row Save, top-bar switcher + Workspace toggle, unified sidebar, guards, beforeunload |
| `apps/web/src/context/SessionContext.tsx` | **MODIFIED** | +`loadSnapshot()` (fresh session + restore + hydrate; see 2.2.3) |

**No changes to:** `lib/versionCache.ts`, `components/ChatPanel.tsx`, `components/DiffViewer.tsx`, `components/UploadPanel.tsx` (upload guard wired from page level).

---

## 7. Verification

Run API with DB + Auth0 env, web via `npm run dev`, log in with a test account.

1. **Login:** switcher shows `default` active; JSONs tab lists 0/5.
2. **Save new:** upload JSON, create a version, Save → dialog shows "+1 version" when edited; save with tag `demo` → appears in list `1/5`.
3. **Load:** switch away (new session), reopen `demo` → versions restored, latest loaded in editor, Versions tab populated.
4. **Guard:** edit JSON, click another document → modal appears; Cancel keeps editor; Discard switches; Save… persists then switches.
5. **Limits:** 5 documents → save-as-new disabled + 409 toast path; 5 versions → dialog blocks with guidance.
6. **Duplicate tag:** save with existing tag → inline error, dialog stays open.
7. **Anonymous:** logged out — upload/version work, Save → login modal, no `/api/workspaces` request in the network tab.
8. **Reload:** active workspace + document restored from localStorage.
9. **Regression:** chat SSE, diff accept/reject, export, IndexedDB restore after backend restart all behave as before.

---

*End of implementation guide. Feature branch: `workspace`.*
