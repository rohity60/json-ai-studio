# Frontend Requirements — JSON AI Studio Explain Feature

Derived from PRD `explain-feature.prd`. Only what the **client / UI layer** must implement.

---

## 1. UI Changes

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | Add "Explain" button to the left panel header (next to "New Session" button). | MVP |
| U-02 | When JSON is empty (`Object.keys(json).length === 0`), "Explain" button is disabled. | MVP |
| U-03 | Clicking "Explain" calls `POST /api/explain` with current `workingJson` and `sessionId`. | MVP |
| U-04 | On success, the right panel switches to an "AI Explanation" view showing the markdown response. | MVP |
| U-05 | A "Back to JSON" button in the explanation view switches the right panel back to the JSON tree. | MVP |
| U-06 | A "Back to Diff" button also available in the explanation view (for users who were viewing diffs). | MVP |
| U-07 | While streaming/loading, show a spinner + "Explaining..." text. | MVP |
| U-08 | On error, show a toast notification + "Retry" button in the right panel. | MVP |
| U-09 | The explanation is ephemeral — not saved to session state. Uploading new JSON or creating a new session clears it. | MVP |

---

## 2. Component Details

### 2.1 `ExplainPanel.tsx` — New Component

**Location:** `apps/web/src/components/ExplainPanel.tsx`

Props:
- `sessionId: string | null`
- `workingJson: Record<string, any>`
- `apiKey: string`

Behavior:
1. Renders an "Explain" button initially.
2. On click, calls `api.explain(sessionId, workingJson, apiKey)`.
3. While loading: shows spinner + "Explaining..." text.
4. On success: renders the markdown response using `react-markdown`.
5. On error: shows error message + "Retry" button.
6. Has a "Back" button to return to JSON/Diff views.

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

The `explainJson()` method:
1. Calls `api.explain(sessionId, workingJson, apiKey)`.
2. Sets `explainMarkdown` to the returned string.
3. Sets `loading` to `false` when done.
4. On error, sets `error` to the error message.

### 2.4 `page.tsx` — Wire Explain Button + Panel

**Location:** `apps/web/src/app/page.tsx`

Changes:
1. Import `ExplainPanel` component.
2. Import `explainMarkdown` and `explainJson` from `useSession()`.
3. Add "Explain" button in the header (next to "New Session").
4. In the right panel tab content, add a third tab: "Explanation".
5. When "Explanation" tab is active, render `<ExplainPanel />` or show the stored markdown.

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
7. Right panel switches to "Explanation" tab, renders markdown
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
