# JSON AI Studio — Explain Feature Frontend Implementation Guide

**Feature branch:** `explain-feature`
**Requirements:** `requirements.md`

---

## 1. Architecture

```
User clicks "Explain" button (left panel header)
   → SessionContext.explainJson()
     → api.explain(sessionId, workingJson, apiKey)
       → POST /api/explain {sessionId, workingJson}
   → Response: markdown string
   → setState({ ...prev, explainMarkdown: markdown, loading: false })
   → Right panel switches to "Explanation" tab
   → <ExplainPanel markdown={markdown} /> renders
```

**Key principle:** The explain flow is a separate state field (`explainMarkdown`) in `SessionState`. It does not interfere with `workingJson` or `baselineJson`. The right panel has three tabs: "Working JSON", "Diff Viewer", "Explanation".

---

## 2. Component Details

### 2.1 `package.json` — Add `react-markdown` Dependency

**Location:** `apps/web/package.json`
**Action:** Add to `dependencies`.

```json
"react-markdown": "^9.0.1",
```

Then run: `npm install react-markdown @types/react-markdown`

### 2.2 `api.ts` — Add `explain()` Client

**Location:** `apps/web/src/lib/api.ts`
**Action:** Append before the last closing brace.

```typescript
export async function explain(
    sessionId: string,
    workingJson: Record<string, any>,
    apiKey: string,
): Promise<string> {
    const res = await fetch(`${BASE}/explain`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify({sessionId, workingJson}),
    });
    if (!res.ok) throw new Error(`Explain failed: ${await res.text()}`);
    return await res.text();
}
```

### 2.3 `SessionContext.tsx` — Add Explain State + Method

**Location:** `apps/web/src/context/SessionContext.tsx`

**Step 1:** Add to `SessionState` type (around line 16):

```typescript
explainMarkdown: string | null;
```

**Step 2:** Add to `SessionContextValue` type (around line 31):

```typescript
explainJson: () => Promise<void>;
```

**Step 3:** Initialize in `useState` (around line 50):

```typescript
explainMarkdown: null,
```

**Step 4:** Add the `explainJson` method before `exportSession`:

```typescript
const explainJson = useCallback(async () => {
    if (!state.sessionId || !Object.keys(state.workingJson).length) return;
    setState((prev) => ({ ...prev, loading: true }));
    try {
        const markdown = await api.explain(
            state.sessionId, state.workingJson, apiKey,
        );
        setState((prev) => ({
            ...prev,
            explainMarkdown: markdown,
            loading: false,
            error: null,
        }));
    } catch (err: any) {
        toast.error(String(err));
        setState((prev) => ({ ...prev, error: String(err), loading: false }));
    }
}, [state.sessionId, state.workingJson, apiKey]);
```

**Step 5:** Reset `explainMarkdown` when session changes. In `uploadJson` callback, add `explainMarkdown: null` to the state update. In `createSession` success, add `explainMarkdown: null`.

**Step 6:** Add to `SessionContext.Provider` value (around line 439):

```typescript
explainJson,
```

### 2.4 `ExplainPanel.tsx` — New Component

**Location:** `apps/web/src/components/ExplainPanel.tsx`

```tsx
'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, RotateCcw, Sparkles } from 'lucide-react';

interface ExplainPanelProps {
    markdown: string;
    onBack: () => void;
    onRetry?: () => void;
    loading?: boolean;
    error?: string | null;
}

export default function ExplainPanel({
    markdown,
    onBack,
    onRetry,
    loading = false,
    error = null,
}: ExplainPanelProps) {
    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center">
                    <Sparkles className="w-8 h-8 mx-auto mb-2 text-purple-500 animate-pulse" />
                    <p className="text-sm text-muted-foreground">Explaining...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-4">
                <p className="text-sm text-red-500">{error}</p>
                {onRetry && (
                    <button
                        onClick={onRetry}
                        className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
                    >
                        <RotateCcw className="w-4 h-4" />
                        Retry
                    </button>
                )}
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            <div className="flex items-center justify-between border-b px-4 py-2">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-purple-600" />
                    <span className="text-sm font-medium">AI Explanation</span>
                </div>
                <button
                    onClick={onBack}
                    className="px-3 py-1 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                    <ArrowLeft className="w-3 h-3" />
                    Back
                </button>
            </div>
            <div className="flex-1 overflow-auto p-4 prose prose-sm max-w-none">
                <ReactMarkdown>{markdown}</ReactMarkdown>
            </div>
        </div>
    );
}
```

### 2.5 `page.tsx` — Wire Explain Button + Explanation Tab

**Location:** `apps/web/src/app/page.tsx`

**Step 1:** Add imports:

```tsx
import ExplainPanel from '@/components/ExplainPanel';
import { Sparkles } from 'lucide-react';
```

**Step 2:** Destructure new values from `useSession()`:

```tsx
const { state, createSession, uploadJson, sendMessage, explainJson } = useSession();
```

**Step 3:** Add "Explain" button in the header, next to "New Session":

```tsx
{Object.keys(json).length > 0 && (
    <button
        onClick={() => explainJson()}
        disabled={state.loading}
        className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1"
    >
        <Sparkles className="w-4 h-4" />
        Explain
    </button>
)}
```

**Step 4:** Add "Explanation" tab to the right panel tab bar:

```tsx
<button
    onClick={() => setPreviewTab('explain')}
    className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
        previewTab === 'explain' ? 'bg-purple-100 text-purple-700' : 'hover:bg-gray-100'
    }`}
>
    Explanation
</button>
```

**Step 5:** Add explanation tab content:

```tsx
{previewTab === 'explain' && (
    <ExplainPanel
        markdown={state.explainMarkdown || ''}
        onBack={() => setPreviewTab('preview')}
        onRetry={() => explainJson()}
        loading={state.loading}
        error={state.error}
    />
)
```

**Step 6:** Also allow going back to diff from explanation:

The "Back" button in `ExplainPanel` should cycle: if user was on "preview" before, go back to "preview". If they were on "diff", go back to "diff". For MVP, simple back to "preview" is sufficient.

---

## 3. Data Flow

### 3.1 Happy Path

```
1. User uploads JSON → workingJson populated, explainMarkdown = null
2. "Explain" button enabled (Object.keys(json).length > 0)
3. User clicks "Explain"
4. explainJson() called → setState({ loading: true })
5. api.explain() → POST /api/explain → LLM → markdown string
6. setState({ explainMarkdown: markdown, loading: false })
7. Right panel tab switches to 'explain'
8. <ExplainPanel markdown={markdown} /> renders with ReactMarkdown
```

### 3.2 Error Path

```
1. User clicks "Explain"
2. api.explain() throws (network error, 500, etc.)
3. toast.error(String(err))
4. setState({ error: String(err), loading: false })
5. ExplainPanel renders error state with "Retry" button
6. User clicks "Retry" → step 3 repeats
```

### 3.3 Clear on Session Change

```
1. User uploads new JSON
2. uploadJson() resets workingJson, sets explainMarkdown: null
3. Right panel returns to "Working JSON" tab
```

---

## 4. Error Handling

| Scenario | Response |
|----------|----------|
| `explainJson()` called with no sessionId | Early return, no API call |
| `explainJson()` called with empty workingJson | Early return, no API call |
| API returns 401 | Toast "Auth required", explainMarkdown stays null |
| API returns 404 | Toast "Session not found", explainMarkdown stays null |
| API returns 500 | Toast "Explain failed: ...", ExplainPanel shows error + Retry |
| Network error | Toast error message, ExplainPanel shows error + Retry |
| New session created | explainMarkdown reset to null, panel returns to JSON view |

---

## 5. Assumptions & Constraints

1. **Ephemeral explanations.** `explainMarkdown` is not persisted. It resets on session change.
2. **Single explanation per session.** The latest explanation overwrites the previous one. No history of past explanations.
3. **`react-markdown` dependency.** Must be installed via `npm install`. Not in existing dependencies.
4. **Prose styling.** The `prose` Tailwind class is used for markdown rendering. Ensure `@tailwindcss/typography` plugin is available, or the prose classes won't apply. For MVP, raw markdown text is acceptable without typography styling.
5. **No streaming on UI.** The explain API is non-streaming. The user waits for the full response. The loading spinner provides feedback during the wait.
6. **Back button goes to JSON view.** For MVP, "Back" always returns to "Working JSON" tab. No memory of previous tab state.

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `apps/web/package.json` | **MODIFIED** | Add `react-markdown` dependency |
| `apps/web/src/lib/api.ts` | **MODIFIED** | Add `explain()` client function |
| `apps/web/src/context/SessionContext.tsx` | **MODIFIED** | Add `explainMarkdown` state + `explainJson()` method |
| `apps/web/src/components/ExplainPanel.tsx` | **NEW** | Markdown rendering panel component |
| `apps/web/src/app/page.tsx` | **MODIFIED** | Add "Explain" button + "Explanation" tab + wire ExplainPanel |

**No changes to:** `UploadPanel.tsx`, `ChatPanel.tsx`, `JSONTree.tsx`, `DiffViewer.tsx`, `VersionSidebar.tsx`.

---

## 7. Verification

### Manual Tests

1. **Happy path:** Upload JSON. Click "Explain". Verify right panel shows markdown with ## Summary, ## Main Objects, etc.
2. **No JSON:** On empty session, "Explain" button is disabled.
3. **Error handling:** Kill backend server. Click "Explain". Verify toast error + "Retry" button.
4. **Retry:** After error, click "Retry". Verify API call repeats.
5. **Back button:** Click "Back" in ExplainPanel. Verify right panel returns to JSON tree.
6. **Clear on upload:** Upload new JSON. Verify "Explain" button works with new data.
7. **Loading state:** Click "Explain" on large JSON. Verify spinner shows during LLM call.
8. **New session:** Create new session. Verify explainMarkdown cleared, panel returns to JSON.

---

*End of implementation guide. Feature branch: `explain-feature`.*
