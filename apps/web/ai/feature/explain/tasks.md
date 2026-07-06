# Explain Feature (Frontend) — Task List

**Feature branch:** `explain-feature`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `react-markdown` to `apps/web/package.json` dependencies, run `npm install` | pending |
| 2 | Add `explain()` client to `apps/web/src/lib/api.ts` — POST `/api/explain`, returns markdown string | pending |
| 3 | Add `explainMarkdown: string | null` to `SessionState` type in `SessionContext.tsx` | pending |
| 4 | Add `explainJson()` method to `SessionContext.tsx` — calls `api.explain()`, sets `explainMarkdown` state, handles errors | pending |
| 5 | Reset `explainMarkdown: null` in `uploadJson()` and `createSession()` success paths | pending |
| 6 | Add `explainJson` to `SessionContext.Provider` value in `SessionContext.tsx` | pending |
| 7 | Create `apps/web/src/components/ExplainPanel.tsx` — markdown rendering panel with loading/error/success states, "Back" button | pending |
| 8 | Wire "Explain" button in `page.tsx` header — next to "New Session", disabled when no JSON | pending |
| 9 | Add "Explanation" tab to right panel tab bar in `page.tsx` — renders `<ExplainPanel />` | pending |
| 10 | Verify — run app, upload JSON, click "Explain", verify markdown renders in right panel | pending |

---

*Total: 10 tasks. Sequential: 1→2→3→4→5→6→7→8→9→10.*
