# Frontend Requirements — JSON AI Studio MVP

Derived from PRD v1.0. Only what the **client / UI layer** must implement.
Technical decisions are documented in `docs/adr/`.

---

## 1. Layout & Navigation

| # | Requirement | Priority |
|---|-------------|----------|
| L-01 | Root layout with site title "JSON AI Studio" and tagline | MVP ✅ |
| L-02 | Responsive two-panel layout: left (chat/upload) + right (diff/preview) | MVP ✅ |
| L-03 | Persistent session/version badge in header or sidebar | MVP ✅ |

## 2. JSON Upload & Parsing UI

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | Drag-and-drop zone for `.json` file upload | MVP ✅ |
| U-02 | Textarea input as alternative paste method for raw JSON | MVP ✅ |
| U-03 | Client-side syntax validation feedback on paste/upload (show error line/column) | MVP ✅ |
| U-04 | Render the uploaded JSON as an expandable **tree view** | MVP ✅ |
| U-05 | "Load existing session" and "Import previous version" placeholders for future wiring | MVP ✅ |

## 3. Conversational Editing Workspace (SSE)

> **Streaming context**: The backend returns SSE events — `thinking` → `diff` (multiple) → `complete`. The frontend must handle all three phases in sequence.

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | Persistent chat panel displaying full conversation history (user messages + AI streaming responses) | MVP ✅ |
| C-02 | Input text area with "Send" button; Enter to submit, Shift+Enter for newline | MVP ✅ |
| C-03 | On send, POST to `/api/chat` and receive SSE stream via `fetch` + `ReadableStream` | MVP ✅ |
| C-04 | **Streaming phase handling**: render thinking text inline → accumulate diff entries → on `complete`, update JSON preview panel | MVP ✅ |
| C-05 | Placeholder examples (inline hint): "Increase timeout from 30 to 60", "Add retry count of 5", etc. | MVP ✅ |
| C-06 | Auto-scroll chat to bottom on new messages and during streaming | MVP ✅ |

## 4. Visual Diff Viewer

| # | Requirement | Priority |
|---|-------------|----------|
| D-01 | Display diff between "before" and "after" versions of the JSON | MVP ✅ |
| D-02 | Color-coded diff: green for added, red for deleted, yellow for modified | MVP ✅ |
| D-03 | Side-by-side comparison view for the JSON tree | MVP ✅ |
| D-04 | Tree-level expand/collapse toggles within the diff | MVP ✅ |
| D-05 | Search/filter changes by keyword or change type (added/modified/deleted) | MVP ✅ |
| D-06 | **Library**: `react-diff-viewer` (v3.1.1) for unified/split diff rendering | MVP ✅ |
| D-07 | **View toggle**: Switch between "Diff Viewer" (unified split view) and "Side by Side" (JsonView trees) | MVP ✅ |
| D-08 | **Word-level diff**: `DiffMethod.WORDS` for inline word-level highlighting | MVP ✅ |
| D-09 | **Focused view**: `showDiffOnly={true}` + `extraLinesSurroundingDiff={3}` to show only changed lines with context | MVP ✅ |
| D-10 | **Legend bar**: Color chips (Added/Modified/Deleted) with toggle bar in header | MVP ✅ |

Implementation: `DiffViewer.tsx` uses `ReactDiffViewer` component with `oldCode`/`newCode` as stringified JSON. Two view modes — unified split view (green/red lines via library) and side-by-side JsonView fallback. Change list with accept/reject buttons preserved below the viewer.

## 5. Incremental Approval Workflow UI

| # | Requirement | Priority |
|---|-------------|----------|
| A-01 | Per-change toggle: **Accept** / **Reject** for each proposed modification | MVP ✅ |
| A-02 | Global actions: "Accept All" / "Reject All" | MVP ✅ |
| A-03 | After acceptance, update the working JSON tree and refresh the view | MVP ✅ |

## 6. Version Management UI

| # | Requirement | Priority |
|---|-------------|----------|
| V-01 | Sidebar or dropdown listing all versions (original, working, approved) | MVP ✅ |
| V-02 | Click a version to restore / preview it in the diff viewer | MVP ✅ |
| V-03 | Visual indicator for the currently active / "working" version | MVP ✅ |
| V-04 | Refresh versions list from backend via API call | MVP ✅ |
| V-05 | `POST /api/sessions/{id}/versions/select` — call backend to select a version as working baseline | MVP |
| V-06 | On select success: reset `workingJson` AND `baselineJson` from response, clear `conversationHistory` | MVP |
| V-07 | Mark the selected version with an "active" indicator in the version sidebar | MVP |
| V-08 | After selection, chat turns branch from the new baseline (same as after upload or accept-all) | MVP |
| V-09 | Detect unsaved local changes: compare current `workingJson` vs last saved baseline. If different, show confirmation modal before calling select endpoint | MVP |
| V-10 | Confirmation modal: "You have unsaved changes. Save before switching version?" Options: "Save & Continue" (calls createVersion then select), "Continue Without Saving" (proceeds directly to select) | MVP |

## 6.5 Version Selection — Frontend Details

When user clicks a version in the sidebar, the frontend must call the backend endpoint and update all local state.

### F7 — Select Version: Call Backend Endpoint

- `selectVersion(versionId)` in SessionContext replaces the current no-op inline state update
- Sends `POST /api/sessions/{sid}/versions/select` with body `{ "versionId": "v3" }`
- Waits for backend response before updating local state

### F8 — Select Version: Reset Local State

- On success: set `workingJson` = response `working_json`, `baselineJson` = response `baseline_json`
- Clear `conversationHistory` to `[]`
- Set `activeVersionId` = response `active_version_id`
- Version list sidebar marks the selected version with an "active" badge/indicator

### F9 — Select Version: UX Behavior

- Show loading spinner during the API call
- On failure: show toast with error message
- After selection, the diff viewer shows no diffs (baseline == working)
- Chat input is enabled; new messages branch from the new baseline
- The selected version is visually highlighted in the version sidebar

### Updated State Management

| Field | Source | Purpose |
|-------|--------|---------|
| `workingJson` | Backend response `working_json` | DiffViewer "after" panel + JSONTree |
| `baselineJson` | Backend response `baseline_json` | DiffViewer "before" panel |
| `activeVersionId` | Backend response `active_version_id` | Sidebar "active" badge |
| `conversationHistory` | Cleared on version-select | Fresh branch from selected version |

### F10 — Unsaved Changes Detection Before Version Select

Before calling `POST /api/sessions/{id}/versions/select`, compare the current `workingJson` in local state with the last saved baseline. If they differ, show a confirmation modal.

- Deep-compare `workingJson` vs `baselineJson` (or vs the selected version's `json_data` if the user already knows which version they want). For MVP: compare `workingJson` vs `baselineJson`.
- If identical → proceed directly to API call (no modal).
- If different → show modal.

### F11 — Unsaved Changes Confirmation Modal

Modal UI:

```
Title: "Unsaved Changes"
Body: "You have unsaved changes. Save before switching to this version?"

[Save & Continue]  [Continue Without Saving]
```

- **"Save & Continue"**: Calls `POST /api/sessions/{id}/versions` first (creates a snapshot of current state), THEN calls `POST /api/sessions/{id}/versions/select` with the target versionId. Shows the created version in the sidebar.
- **"Continue Without Saving"**: Skips the createVersion call, proceeds directly to `selectVersion`. Discards unsaved changes. No toast — silent discard.

### F12 — Modal Implementation Details

- Modal is a centered overlay with backdrop. Uses existing `sonner` toast for non-modal feedback.
- Modal blocks all interaction with the rest of the UI until dismissed.
- Both buttons are disabled only while their respective API calls are in flight.
- "Save & Continue" button shows a mini-spinner during the createVersion call.
- After either action completes, the modal closes and the version selection proceeds normally.
- If `createVersion` fails during "Save & Continue", show error toast and keep modal open. User can retry or cancel.

## 7. Export

| # | Requirement | Priority |
|---|-------------|----------|
| E-01 | Download button for current (approved) JSON as pretty-printed file | MVP ✅ |
| E-02 | Download option for minified JSON (toggle or secondary button) | MVP ✅ |

## 8. State Management

| # | Requirement | Priority |
|---|-------------|----------|
| S-01 | Global client state holds: current JSON, conversation history, diff result, active version | MVP ✅ |
| S-02 | Session recovery: persist conversation + working JSON in `localStorage` to survive refresh | MVP ✅ |

## 8.5 Bidirectional Diff State Synchronization

Frontend reads `baseline_json` and `working_json` from backend responses. Never computes "before" from local state. Every JSON-affecting response returns both values + remaining diff list.

### F1 — Upload Response: Populate Diff Viewer Before/After ✅
- `uploadJson()` reads `before` and `after` from response
- Set `workingJson` = `after`
- DiffViewer auto-populates: before panel = `before`, after panel = `after`
- Both panels show identical JSON initially

### F2 — Chat Response: Render Baseline vs Working ✅
- `sendMessage()` reads `baseline_json` → store as `baselineJson` (replaces local useState)
- Reads `working_json` → store as `workingJson`
- Reads `diffs` → append to conversation history
- DiffViewer renders: before = `baseline_json`, after = `working_json`

### F3 — Accept All: Merge Both Panels ✅
- `workingJson` = `baseline_json` = `working_json` (all identical from response)
- Clear all diffs from last conversation turn
- DiffViewer: both panels show identical JSON, no change list

### F4 — Reject All: Restore Baseline View ✅
- `workingJson` = `baseline_json` (both identical from response)
- Clear last turn's diffs
- DiffViewer: both panels show baseline, no changes

### F5 — Accept Single Diff: Update Working + Diff List ✅
- `workingJson` = new `working_json` from response
- Remove accepted diff from last turn's diff list
- DiffViewer: before = baseline, after = new_working, change list shrinks

### F6 — Reject Single Diff: Reverse Working + Diff List ✅
- `workingJson` = new `working_json` from response
- Remove rejected diff from last turn's diff list
- DiffViewer: before = baseline, after = new_working, change list shrinks

### Updated State Management ✅
- Remove local `prevJson` useState from `page.tsx` — derive "before" from `baseline_json` in responses
- `SessionContext` reads `baseline_json` from every upload/chat/accept/reject response
- DiffViewer always receives `before` and `after` from backend — never computes from history
- State table:

| Field | Source | Purpose |
|-------|--------|---------|
| `baseline_json` | Backend response | DiffViewer "before" panel |
| `working_json` | Backend response | DiffViewer "after" panel + JSONTree |
| `diffs` | Backend response | Change list with accept/reject per entry |

## 9. UX / Quality

| # | Requirement | Priority |
|---|-------------|----------|
| X-01 | Loading spinners while awaiting backend responses (chat, diff, validation) | MVP ✅ |
| X-02 | Empty states and tooltips explaining each section to first-time users | MVP ✅ |
| X-03 | Toast notifications for success / error events from the API | MVP ✅ |

## 10. Version Selection — Architecture & Data Flow

### Architecture

```
User clicks version in sidebar
      → SessionContext.selectVersion(versionId)
      → deepEqual(workingJson, baselineJson)
      → If different: show UnsavedChangesModal
      → If same: call API directly
      → UnsavedChangesModal:
          "Save & Continue" → api.createVersion(label) → api.selectVersion(versionId)
          "Continue Without Saving" → api.selectVersion(versionId)
      → On success: update workingJson, baselineJson, clear conversationHistory, set activeVersionId
```

**Key principle:** The frontend must detect unsaved local changes before calling the backend select endpoint. A modal gives the user two options: save the current state first, or discard changes.

### Data Flow

#### D-01 — Happy Path: No Unsaved Changes

```
1. User clicks version "v2" in sidebar
2. selectVersion("v2") called
3. deepEqual(workingJson, baselineJson) → true (no unsaved changes)
4. API call: POST /api/sessions/abc123/versions/select { versionId: "v2" }
5. Response: { working_json: {...}, baseline_json: {...}, active_version_id: "v2" }
6. setState updates workingJson, baselineJson, conversationHistory=[], activeVersionId
7. UI re-renders with new baseline
```

#### D-02 — Happy Path: With Unsaved Changes, User Saves

```
1. User modifies JSON via chat. workingJson ≠ baselineJson.
2. User clicks version "v2" in sidebar.
3. selectVersion("v2") called.
4. deepEqual(workingJson, baselineJson) → false → show modal.
5. User clicks "Save & Continue".
6. POST /api/sessions/abc123/versions { label: "Auto-save before switch" } → creates v3.
7. POST /api/sessions/abc123/versions/select { versionId: "v2" } → selects v2.
8. State updated. Modal closes.
```

#### D-03 — Happy Path: With Unsaved Changes, User Discards

```
1. User modifies JSON via chat. workingJson ≠ baselineJson.
2. User clicks version "v2" in sidebar.
3. selectVersion("v2") called.
4. deepEqual(workingJson, baselineJson) → false → show modal.
5. User clicks "Continue Without Saving".
6. POST /api/sessions/abc123/versions/select { versionId: "v2" } → selects v2.
7. State updated. Modal closes. Unsaved changes discarded silently.
```

#### D-04 — Error: Save Fails

```
1. Modal open. User clicks "Save & Continue".
2. POST /api/sessions/abc123/versions fails (e.g. network error).
3. Toast: "Failed to save. Please try again."
4. Modal stays open. User can retry or click "Continue Without Saving".
```

### Error Handling

| Scenario | Response |
|----------|----------|
| `selectVersion` API call fails | Toast error, modal stays open, user can retry or discard |
| `createVersion` API call fails (Save & Continue) | Toast "Failed to save", modal stays open |
| No sessionId (stale state) | Early return, no API call |
| Modal dismissed by clicking backdrop | Discard and continue (same as "Continue Without Saving") |

### Component Details

#### `api.ts` — Add `selectVersion` Client

```tsx
export async function selectVersion(
    sessionId: string,
    versionId: string,
    apiKey: string,
): Promise<{
    working_json: Record<string, any>;
    baseline_json: Record<string, any>;
    active_version_id: string | null;
    versions: any[];
    conversation_history: any[];
}> {
    const res = await fetch(`/api/sessions/${sessionId}/versions/select`, {
        method: 'POST',
        headers: {
             'Content-Type': 'application/json',
             'X-API-Key': apiKey,
         },
        body: JSON.stringify({ versionId }),
     });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `Failed to select version: ${res.status}`);
     }
    return res.json();
}
```

#### `SessionContext.tsx` — Replace No-Op `selectVersion`

```tsx
const selectVersion = useCallback(async (versionId: string) => {
    // Check for unsaved changes
    if (!deepEqual(state.workingJson, state.baselineJson || {})) {
        setPendingVersionId(versionId);
        setUnsavedChangesModalOpen(true);
        return;
     }
    await callSelectVersion(versionId);
}, [state.sessionId, apiKey, state]);
```

#### `UnsavedChangesModal.tsx` — New Component

```tsx
// Modal UI:
// Title: "Unsaved Changes"
// Body: "You have unsaved changes. Save before switching to this version?"
// Buttons: [Save & Continue] [Continue Without Saving]
// - "Save & Continue" calls createVersion then selectVersion
// - "Continue Without Saving" calls selectVersion directly, discards silently
```

### Assumptions & Constraints

1. **Deep equality via JSON.stringify.** For MVP, `JSON.stringify(a) === JSON.stringify(b)` is sufficient. No deep-equal library.
2. **Modal blocks all interaction.** Fixed overlay with `z-50` and `bg-black/40` backdrop. No other UI interaction until dismissed.
3. **Auto-save label is fixed.** "Auto-save before switch". No user input for label in MVP.
4. **Discard is silent.** No toast on discard. User explicitly chose to discard.
5. **`selectVersion` signature changes.** From `(version: any) => void` to `(versionId: string) => Promise<void>`. All callers must update.
6. **`activeVersionId` in state.** New field in `SessionState` type. Used to highlight the active version in the sidebar.
7. **Backend always succeeds.** The unsaved-changes guard is frontend-only. Backend always accepts the select request.

## 11. Excluded from MVP (Frontend)

- Git integration UI
- Multi-file editing panels
- Team collaboration / commenting overlays
- Enterprise governance controls