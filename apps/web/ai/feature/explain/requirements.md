# Frontend Requirements — JSON AI Studio Explain Feature

Derived from PRD `explain-feature.prd`. Only what the **client / UI layer** must implement.

---

## 1. UI Changes

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | Add "Explain" button at the bottom of the Working JSON panel, rendered below the JSON tree. | MVP |
| U-02 | When JSON is empty (`Object.keys(json).length === 0`), "Explain" button is hidden. | MVP |
| U-03 | Clicking "Explain" calls `POST /api/explain` with current `workingJson` and `sessionId`. Uses a dedicated `explaining` flag — must NOT set the global `loading` flag (the provider unmounts the app while `loading` is true). | MVP |
| U-04 | The explanation renders inline in a scrollable card (`max-h` + `overflow-y-auto`) below the Working JSON tree — no separate tab or view. Card is hidden until an explain is triggered. | MVP |
| U-05 | Markdown renders with explicit element styling (headings, `strong` highlight, code chips, tables, blockquotes) via ReactMarkdown `components` — the project has no `@tailwindcss/typography` plugin, so `prose` classes do nothing. | MVP |
| U-07 | While streaming/loading, show a spinner + "Explaining..." text inside the card. | MVP |
| U-08 | On error, show a toast notification + "Retry" button inside the card. | MVP |
| U-09 | The explanation is ephemeral — not saved to session state. Uploading new JSON or creating a new session clears it. | MVP |

---

## 2. Component Details

### 2.1 `ExplainPanel.tsx` — New Component

**Location:** `apps/web/src/components/ExplainPanel.tsx`

Props:
- `markdown: string`
- `onRetry?: () => void`
- `loading?: boolean`
- `error?: string | null`

Behavior:
1. Renders as an inline card with header ("AI Explanation" + Refresh button) and a scrollable body (`max-h-[45vh] overflow-y-auto`).
2. While loading: shows spinner + "Explaining..." text.
3. On success: renders the markdown via `react-markdown` with a custom `components` map for styling.
4. On error: shows error message + "Retry" button.
5. Parent (`page.tsx`) only mounts it when `explaining || explainError || explainMarkdown`.

### 2.2 `api.ts` — Add `explain()` Client

**Location:** `apps/web/src/lib/api.ts`

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

### 2.3 `SessionContext.tsx` — Add `explainMarkdown` State

**Location:** `apps/web/src/context/SessionContext.tsx`

Add to `SessionState`:
```typescript
explainMarkdown: string | null;
```

Add to `SessionContextValue`:
```typescript
explainJson: () => Promise<void>;
```

Also add dedicated explain flags (do not reuse the global `loading`/`error`):
```typescript
explaining: boolean;
explainError: string | null;
```

The `explainJson()` method:
1. Sets `explaining: true`, clears `explainError`.
2. Calls `api.explain(sessionId, workingJson, apiKey)`.
3. Sets `explainMarkdown` to the returned string, `explaining: false`.
4. On error, sets `explainError` to the error message, `explaining: false`.

### 2.4 `page.tsx` — Wire Explain Button + Panel

**Location:** `apps/web/src/app/page.tsx`

Changes:
1. Import `ExplainPanel` component.
2. Import `explainMarkdown` and `explainJson` from `useSession()`.
3. Add "Explain" button below the JSON tree in the Working JSON tab (visible only when JSON is non-empty).
4. Render `<ExplainPanel />` inline below the button, inside the Working JSON tab, only when `state.explaining || state.explainError || state.explainMarkdown`. No extra tab.

---

## 3. Data Flow

### 3.1 Happy Path

```
1. User uploads JSON → workingJson populated in state
2. "Explain" button becomes enabled (Object.keys(json).length > 0)
3. User clicks "Explain"
4. Frontend calls api.explain(sessionId, workingJson, apiKey)
5. Backend calls LLM, returns markdown
6. Frontend sets explainMarkdown state
7. Styled markdown renders in the scrollable card below the Working JSON tree
```

### 3.2 Error Path

```
1. User clicks "Explain"
2. API call fails (network error, 500, etc.)
3. Frontend shows error toast
4. Right panel shows "Explanation failed. Retry" message
5. User clicks "Retry" → repeats step 3
```

### 3.3 Clear on Session Change

```
1. User uploads new JSON or creates new session
2. workingJson resets to {}
3. explainMarkdown resets to null
4. Right panel returns to default (JSON tree)
```

---

## 4. Excluded from MVP

- Explain selected node (partial JSON)
- Explain path (right-click context menu)
- Multiple detail levels (beginner / developer / expert)
- Architecture diagram rendering
- Mermaid diagram rendering
- Save explanation to history
- Export explanation as file
- Copy explanation to clipboard
- Share explanation link

---

*End of requirements. Feature branch: `explain-feature`.*
