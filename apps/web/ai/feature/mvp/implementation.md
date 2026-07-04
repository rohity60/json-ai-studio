# JSON AI Studio — Version Selection Frontend Implementation Guide

**Feature branch:** `mvp`
**Requirements:** `requirements.md`

---

## 1. Architecture

```
User clicks version in sidebar
     → SessionContext.selectVersion(versionId)
     → Compare workingJson vs baselineJson (deep equality)
     → If different: show UnsavedChangesModal
     → If same: call API directly
     → UnsavedChangesModal:
         "Save & Continue" → api.createVersion(label) → api.selectVersion(versionId)
         "Continue Without Saving" → api.selectVersion(versionId)
     → On success: update workingJson, baselineJson, clear conversationHistory, set activeVersionId
```

**Key principle:** The frontend must detect unsaved local changes before calling the backend select endpoint. A modal gives the user two options: save the current state first, or discard changes.

---

## 2. Component Details

### 2.1 `SessionContext.tsx` — Replace No-Op `selectVersion`

**Location:** `apps/web/src/context/SessionContext.tsx`
**Current code (line 365):**

```tsx
const selectVersion = useCallback((version: any) => {
    setState((prev) => ({ ...prev, workingJson: version.json_data || {}, activeVersionId: version.id }));
}, []);
```

**Becomes:**

```tsx
const selectVersion = useCallback(async (versionId: string) => {
    if (!state.sessionId) return;
    
    try {
        const data = await api.selectVersion(state.sessionId, versionId, apiKey);
        setState({
            ...state,
            workingJson: data.working_json || {},
            baselineJson: data.baseline_json || {},
            conversationHistory: [],
            activeVersionId: data.active_version_id,
            loading: false,
            error: null,
        });
    } catch (err: any) {
        toast.error(String(err));
        setState(prev => ({ ...prev, error: String(err), loading: false }));
    }
}, [state.sessionId, apiKey, state]);
```

### 2.2 `api.ts` — Add `selectVersion` Client

**Location:** `apps/web/src/lib/api.ts`
**Add:**

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

### 2.3 `UnsavedChangesModal.tsx` — New Component

**Location:** `apps/web/src/components/UnsavedChangesModal.tsx`

```tsx
'use client';

import React, { useState } from 'react';

interface UnsavedChangesModalProps {
    isOpen: boolean;
    onSave: () => void;
    onDiscard: () => void;
    saving?: boolean;
}

export function UnsavedChangesModal({ isOpen, onSave, onDiscard, saving }: UnsavedChangesModalProps) {
    const [savingState, setSavingState] = useState(false);

    if (!isOpen) return null;

    const handleSave = async () => {
        setSavingState(true);
        try {
            await onSave();
        } finally {
            setSavingState(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
                <h2 className="text-lg font-semibold mb-2">Unsaved Changes</h2>
                <p className="text-sm text-gray-600 mb-6">
                    You have unsaved changes. Save before switching to this version?
                </p>
                <div className="flex gap-3 justify-end">
                    <button
                        onClick={onDiscard}
                        disabled={savingState}
                        className="px-4 py-2 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
                    >
                        Continue Without Saving
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={savingState}
                        className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                        {savingState ? (
                            <span className="inline-flex items-center gap-2">
                                <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                Saving…
                            </span>
                        ) : (
                            'Save & Continue'
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}
```

### 2.4 `SessionContext.tsx` — Add Unsaved-Changes Detection

**Location:** `apps/web/src/context/SessionContext.tsx`

Add a helper function and modify `selectVersion` to check before calling the API:

```tsx
function deepEqual(a: any, b: any): boolean {
    return JSON.stringify(a) === JSON.stringify(b);
}

const [unsavedChangesModalOpen, setUnsavedChangesModalOpen] = useState(false);
const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);

const selectVersion = useCallback(async (versionId: string) => {
    // Check for unsaved changes
    if (!deepEqual(state.workingJson, state.baselineJson || {})) {
        setPendingVersionId(versionId);
        setUnsavedChangesModalOpen(true);
        return; // Don't proceed until modal is resolved
    }
    // No unsaved changes — proceed directly
    await callSelectVersion(versionId);
}, [state.sessionId, apiKey, state]);

const callSelectVersion = async (versionId: string) => {
    if (!state.sessionId) return;
    try {
        const data = await api.selectVersion(state.sessionId, versionId, apiKey);
        setState({
            ...state,
            workingJson: data.working_json || {},
            baselineJson: data.baseline_json || {},
            conversationHistory: [],
            activeVersionId: data.active_version_id,
            loading: false,
            error: null,
        });
    } catch (err: any) {
        toast.error(String(err));
        setState(prev => ({ ...prev, error: String(err), loading: false }));
    }
};

const handleSaveAndContinue = async () => {
    if (!state.sessionId) return;
    try {
        // Create a snapshot of current state first
        await api.createVersion(state.sessionId, 'Auto-save before switch', state.workingJson, apiKey);
        // Then select the pending version
        if (pendingVersionId) {
            await callSelectVersion(pendingVersionId);
        }
    } catch (err: any) {
        toast.error('Failed to save. Please try again.');
    } finally {
        setUnsavedChangesModalOpen(false);
        setPendingVersionId(null);
    }
};

const handleDiscardAndContinue = () => {
    if (pendingVersionId) {
        callSelectVersion(pendingVersionId).finally(() => {
            setUnsavedChangesModalOpen(false);
            setPendingVersionId(null);
        });
    }
};
```

### 2.5 Add Modal to `SessionProvider` Render

In the `SessionProvider` component, add the modal inline (or as a portal):

```tsx
// Inside SessionProvider's return JSX (before the context provider)
<UnsavedChangesModal
    isOpen={unsavedChangesModalOpen}
    onSave={handleSaveAndContinue}
    onDiscard={handleDiscardAndContinue}
/>
```

### 2.6 `VersionSidebar.tsx` — Update Click Handler

**Location:** `apps/web/src/components/VersionSidebar.tsx` (or wherever versions are rendered)

**Change from:**

```tsx
onClick={() => selectVersion(version)}
```

**To:**

```tsx
onClick={() => selectVersion(version.id)}
```

Pass only the versionId string. The `selectVersion` function in context handles the unsaved-changes detection.

---

## 3. Data Flow

### 3.1 Happy Path — No Unsaved Changes

```
1. User clicks version "v2" in sidebar
2. selectVersion("v2") called
3. deepEqual(workingJson, baselineJson) → true (no unsaved changes)
4. API call: POST /api/sessions/abc123/versions/select { versionId: "v2" }
5. Response: { working_json: {...}, baseline_json: {...}, active_version_id: "v2" }
6. setState updates workingJson, baselineJson, conversationHistory=[], activeVersionId
7. UI re-renders with new baseline
```

### 3.2 Happy Path — With Unsaved Changes, User Saves

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

### 3.3 Happy Path — With Unsaved Changes, User Discards

```
1. User modifies JSON via chat. workingJson ≠ baselineJson.
2. User clicks version "v2" in sidebar.
3. selectVersion("v2") called.
4. deepEqual(workingJson, baselineJson) → false → show modal.
5. User clicks "Continue Without Saving".
6. POST /api/sessions/abc123/versions/select { versionId: "v2" } → selects v2.
7. State updated. Modal closes. Unsaved changes discarded silently.
```

### 3.4 Error — Save Fails

```
1. Modal open. User clicks "Save & Continue".
2. POST /api/sessions/abc123/versions fails (e.g. network error).
3. Toast: "Failed to save. Please try again."
4. Modal stays open. User can retry or click "Continue Without Saving".
```

---

## 4. Error Handling

| Scenario | Response |
|----------|----------|
| `selectVersion` API call fails | Toast error, modal stays open, user can retry or discard |
| `createVersion` API call fails (Save & Continue) | Toast "Failed to save", modal stays open |
| No sessionId (stale state) | Early return, no API call |
| Modal dismissed by clicking backdrop | Discard and continue (same as "Continue Without Saving") |

---

## 5. Assumptions & Constraints

1. **Deep equality via JSON.stringify.** For MVP, `JSON.stringify(a) === JSON.stringify(b)` is sufficient. A proper deep-equal library is overkill for this use case.
2. **Modal blocks all interaction.** Fixed overlay with `z-50` and `bg-black/40` backdrop. No other UI interaction until dismissed.
3. **Auto-save label is fixed.** The "Save & Continue" button creates a version with label "Auto-save before switch". No user input for the label in MVP.
4. **Discard is silent.** No toast on discard. The user explicitly chose to discard.
5. **`selectVersion` signature changes.** From `(version: any) => void` to `(versionId: string) => Promise<void>`. All callers must update.
6. **`activeVersionId` in state.** New field in `SessionState` type. Used to highlight the active version in the sidebar.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/web/src/lib/api.ts` | **MODIFIED** | Add `selectVersion()` client function |
| `apps/web/src/context/SessionContext.tsx` | **MODIFIED** | Replace no-op `selectVersion` with API call + unsaved-changes detection |
| `apps/web/src/components/UnsavedChangesModal.tsx` | **NEW** | Confirmation modal component |
| `apps/web/src/components/VersionSidebar.tsx` | **MODIFIED** | Update click handler to pass `version.id` string |
| `apps/web/ai/feature/mvp/implementation.md` | **NEW** | This document |

---

## 7. Verification

### Manual Tests

1. **No unsaved changes:** Upload JSON. Create version "v1". Select "v1". Verify no modal appears (workingJson === baselineJson). Verify session state updates correctly.
2. **With unsaved changes, save:** Upload JSON. Modify via chat. Create version "v1". Modify again. Click "v1". Verify modal appears. Click "Save & Continue". Verify version created, then selected. Verify state correct.
3. **With unsaved changes, discard:** Same as #2. Click "Continue Without Saving". Verify modal closes, version selected, unsaved changes discarded.
4. **Save fails:** Mock API to return 500 on createVersion. Click "Save & Continue". Verify toast "Failed to save". Verify modal stays open.
5. **Select fails:** Mock API to return 404 on selectVersion. Verify toast error. Verify modal stays open.
6. **Backdrop click:** Open modal. Click backdrop. Verify modal closes and version is selected (discard behavior).

### Code Review Checklist

- [ ] `selectVersion` in `SessionContext` is now `async` and calls the backend API.
- [ ] `deepEqual` helper compares `workingJson` vs `baselineJson` via `JSON.stringify`.
- [ ] Unsaved-changes modal shows when `workingJson !== baselineJson`.
- [ ] "Save & Continue" calls `createVersion` then `selectVersion`.
- [ ] "Continue Without Saving" calls `selectVersion` directly.
- [ ] Modal has proper z-index, backdrop, and disabled states.
- [ ] Error toasts shown on API failures.
- [ ] `SessionState` type has `activeVersionId` field.
- [ ] `VersionSidebar` click handler passes `version.id` string.

---

## 8. Glossary

| Term | Definition |
|------|-----------|
| **Version Selection** | The frontend operation of calling the backend `POST /api/sessions/{id}/versions/select` endpoint and updating local state. |
| **Unsaved Changes** | The condition where `workingJson !== baselineJson`. The user has made local modifications not yet persisted as a version snapshot. |
| **UnsavedChangesModal** | A confirmation dialog that appears before version selection when unsaved changes are detected. |
| **Save & Continue** | Modal action that creates a version snapshot of the current state, then proceeds with the version selection. |
| **Continue Without Saving** | Modal action that discards unsaved changes and proceeds directly with version selection. |
| **Active Version** | The version currently selected, stored in `state.activeVersionId`. Highlighted in the version sidebar. |

---

*End of implementation guide. Feature branch: `mvp`.*
