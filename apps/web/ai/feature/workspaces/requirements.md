# Frontend Requirements — JSON AI Studio Workspaces Feature

Only what the **client / UI layer** must implement. Companion: `apps/api/ai/feature/workspaces/requirements.md`, ADR-0018.

Users organize work into workspaces holding tagged JSON documents with versions. Anonymous flow stays untouched (session + IndexedDB); login unlocks named workspaces; the UI guards unsaved work at every switch point.

---

## 1. UI Changes

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | Workspace switcher dropdown in the header (next to New Session): lists workspaces with active checkmark, per-row `n/5` document count, "New workspace…" entry. | MVP |
| U-02 | Anonymous: switcher shows a single **"Default (local)"** entry + "Log in to create workspaces" CTA. Opening full switcher features, Save, or adding a 2nd JSON triggers the login popup (reuse quota-popup pattern from ADR-0015). | MVP |
| U-03 | JSON document list for the active workspace: tag, version count, updated-at, delete button, `n/5` header counter. Clicking a document loads it (flow 3.3). | MVP |
| U-04 | "Save" button in the toolbar. Anonymous → login CTA popup. Logged-in → SaveDialog (flow 3.4). | MVP |
| U-05 | Unsaved-changes modal (Save… / Discard / Cancel) intercepts: workspace switch, document switch, new upload, New Session, logout. Same visual pattern as the existing version-save prompt. | MVP |
| U-06 | `beforeunload` browser warning when dirty. | MVP |
| U-07 | At limits: controls disable with tooltips ("Workspace full — delete a JSON first" / "Version limit reached"). API `409 limit_exceeded` also surfaces as a toast (belt-and-braces). | MVP |
| U-08 | Per-document and per-version delete with confirm dialog (irreversible action). Deleting the last version of a document is blocked by the API (`409`) — UI offers "Delete JSON instead". | MVP |
| U-09 | Active workspace + active document ids persist in localStorage (next to sessionId); restored on reload. | MVP |
| U-10 | VersionSidebar shows the versions of the loaded document; unchanged for the session-only (anonymous) flow. | MVP |
| U-11 | Loading states: switcher + document list render skeletons; workspace fetches never block the chat panel. | MVP |
| U-12 | Toasts via sonner (ADR-0009), icons via lucide-react (ADR-0010), plain inputs — no form libraries. | MVP |

---

## 2. Component Details

### 2.1 `WorkspaceSwitcher.tsx` — New Component

**Location:** `apps/web/src/components/WorkspaceSwitcher.tsx`

1. Header dropdown listing workspaces from `WorkspaceContext`; active row checkmarked; each row shows `documentCount/5`.
2. "New workspace…" entry → inline name input → `POST /api/workspaces`; `409` duplicate → inline error.
3. Selecting a workspace runs the dirty check (3.6) before switching.
4. Anonymous mode: single "Default (local)" row + login CTA (no API calls).

### 2.2 `JsonDocumentList.tsx` — New Component

**Location:** `apps/web/src/components/JsonDocumentList.tsx`

1. Lists active workspace's documents (`GET /api/workspaces/{ws}/jsons`); header shows `n/5`.
2. Row: tag, version count, updated-at, delete icon (confirm dialog).
3. Click row → dirty check (3.6) → load document (3.3).
4. Renders inside the existing sidebar surface (tab alongside VersionSidebar — one slide-out, two sections/tabs; do not add a second sidebar).

### 2.3 `SaveDialog.tsx` — New Component

**Location:** `apps/web/src/components/SaveDialog.tsx`

1. Workspace: pick existing or type a new name (creates it on save).
2. Tag: text input, prefilled from uploaded filename; required.
3. Version summary: lists session versions to persist; if working JSON differs from the latest version, shows "+1 version (unsaved changes)".
4. Submit: new document → `POST .../jsons` (bulk); existing document → `POST .../jsons/{docId}/versions` (appends only not-yet-persisted snapshots).
5. Inline errors: `409` duplicate tag/name (field-level), `409 limit_exceeded` (dialog-level with delete guidance).
6. Success → toast, document list refreshes, dirty flag clears.

### 2.4 `UnsavedChangesModal.tsx` — New Component

**Location:** `apps/web/src/components/UnsavedChangesModal.tsx`

Props: `onSave`, `onDiscard`, `onCancel`. Shared across all trigger points (U-05). "Save…" opens SaveDialog and continues the pending switch on success.

### 2.5 `WorkspaceContext.tsx` — New Context

**Location:** `apps/web/src/context/WorkspaceContext.tsx`

Separate context — do not bloat `SessionContext`; nests **inside** `SessionProvider` in `app/studio/layout.tsx` (it calls `useSession()` for load/save and dirty tracking).

State:
```typescript
workspaces: WorkspaceSummary[];
activeWorkspaceId: string | null;
documents: JsonDocumentSummary[];
activeDocumentId: string | null;
loadingWorkspaces: boolean;   // dedicated flags — never reuse SessionContext's
loadingDocuments: boolean;    // global `loading` (provider unmounts on it)
```

Actions:
```typescript
refreshWorkspaces(): Promise<void>;
createWorkspace(name: string): Promise<void>;
renameWorkspace(id: string, name: string): Promise<void>;
deleteWorkspace(id: string): Promise<void>;
selectWorkspace(id: string): Promise<void>;      // runs dirty check first
loadDocument(docId: string): Promise<void>;      // fetch + hydrate session (3.3)
saveDocument(input: SaveInput): Promise<void>;   // new or append (3.4)
deleteDocument(docId: string): Promise<void>;
deleteVersion(docId: string, versionId: string): Promise<void>;
```

### 2.6 `SessionContext.tsx` — One New Method

Dirty tracking lives in `WorkspaceContext` (it owns the persistence baseline):
```typescript
dirty: boolean;   // workingJson !== last saved/loaded snapshot, or session versions exist that were never persisted
markClean(): void; // internal — reset after successful Save or document load
```
`WorkspaceContext` reads `workingJson`/`versions` via `useSession()`.

`SessionContext` gains exactly one method — `loadSnapshot(payload)` — which mints a **fresh session**, bulk-restores the given versions + working JSON into it, and hydrates state (mirroring the IndexedDB boot-restore path). Needed because the restore endpoint only accepts sessions with no versions, and a session swap invalidates the other callbacks' closures. SSE, diffs, version flows: untouched.

### 2.7 `api.ts` — Workspace Client Functions

**Location:** `apps/web/src/lib/api.ts`

Fetch wrappers for all 11 workspace routes (bearer token only — these are never called with `X-API-Key`). `401` with `login_available` → surfaces to the login CTA popup handler. Hand-written TS types mirroring the new `spec.yaml` schemas (ADR-0011): `WorkspaceSummary`, `JsonDocumentSummary`, `JsonDocumentDetail`, `JsonVersion`, `SaveJsonRequest`.

---

## 3. Data Flow

### 3.1 Login lands in default workspace

```
1. Login completes → GET /api/workspaces
2. Workspace with isDefault=true becomes active
3. GET /api/workspaces/{ws}/jsons → document list renders
4. No document auto-loaded; editor keeps current session content
```

### 3.2 Switch workspace

```
1. User picks workspace in switcher
2. Dirty? → UnsavedChangesModal (3.6)
3. GET .../jsons for the new workspace → list renders
4. activeDocumentId cleared; localStorage updated
```

### 3.3 Open a document

```
1. Click document row → dirty check (3.6)
2. GET .../jsons/{docId} → document + versions
3. Versions hydrate the session via existing restore seam (ADR-0014)
4. Latest version (highest versionNumber) becomes working JSON
5. VersionSidebar shows the document's versions; markClean()
```

### 3.4 Save

```
1. Save button → anonymous? login CTA popup, stop
2. SaveDialog: workspace pick/create + tag + version summary
3. New document → POST .../jsons (session versions + dirty working snapshot, ≤5 total)
   Existing document → POST .../jsons/{docId}/versions (new snapshots only)
4. Success → toast, list refresh, markClean()
5. 409 → inline error, dialog stays open
```

### 3.5 Anonymous flow (unchanged core)

```
1. Upload + version-create work exactly as today (session + IndexedDB)
2. Save or 2nd JSON → login CTA popup
3. After login, local work still in browser → user saves via 3.4 (no auto-migration)
```

### 3.6 Unsaved-work guard

```
1. Trigger: switch workspace/document, upload, New Session, logout
2. dirty === true → UnsavedChangesModal
   Save…   → SaveDialog; on success continue the pending action
   Discard → continue, drop local changes
   Cancel  → stay, nothing changes
```

---

## 4. States & Edge Cases

- **Backend restart (anonymous)**: existing ADR-0014 IndexedDB restore flow unchanged.
- **401 on a workspace call mid-session** (expired token): login CTA popup; workspace UI reverts to anonymous mode without touching session state.
- **Deleting the active document**: confirm warns; on confirm editor clears to empty state, list refreshes.
- **Workspace list empty response after login** (provisioning race): retry once, then show default-only fallback.
- **Never reuse the global `loading` flag** — provider renders null while `loading` is true and unmounts page-local state; all workspace fetches use dedicated flags.

---

## 5. Excluded from MVP

- Workspace sharing / collaboration UI
- Drag-and-drop of documents between workspaces
- Cross-document version diffing
- Auto-migration of anonymous work at login
- Offline sync of DB workspaces into IndexedDB
- Workspace search/filtering

---

*End of requirements. Feature branch: `workspace`. Implementation files: `components/WorkspaceSwitcher.tsx`, `components/JsonDocumentList.tsx`, `components/SaveDialog.tsx`, `components/UnsavedChangesModal.tsx`, `context/WorkspaceContext.tsx`, `lib/api.ts`, `app/studio/layout.tsx` (provider wiring), `app/studio/page.tsx` (header Save + sidebar tab).*
