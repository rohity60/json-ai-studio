# Frontend Requirements — JSON AI Studio Chat History

Derived from PRD `docs/prd/chat-history.prd`. Only what the **web client** must implement. Backend is authoritative for history and diff status; the client renders and mirrors it.

---

## 1. Types (hand-written mirrors of `openapi/spec.yaml`)

| # | Requirement | Priority |
|---|-------------|----------|
| W-01 | `ChatTurn` type in `lib/api.ts`: `{ id, role: 'user' \| 'assistant', kind: 'message' \| 'boundary', content, created_at, diffs?: DiffEntry[] }`. Replace the `any[]` / ad-hoc `conversationHistory` shape in `SessionContext.tsx`. | MVP |
| W-02 | `DiffEntry` gains `status: 'pending' \| 'accepted' \| 'rejected' \| 'failed'` and `failure_reason?: string`. | MVP |
| W-03 | Drop the client-only `explanation` field on turns — assistant `content` is the explanation. | MVP |

---

## 2. History Hydration & Sync — `context/SessionContext.tsx`

| # | Requirement | Priority |
|---|-------------|----------|
| W-10 | On session load (`GET /api/sessions/{id}`), set `conversationHistory` from the response instead of starting empty. | MVP |
| W-11 | `sendMessage` keeps optimistic rendering (user bubble + streaming assistant bubble). On `complete`, replace the optimistic turns' temp ids with `user_turn_id` / `assistant_turn_id` from the payload. | MVP |
| W-12 | `sendMessage` never sends history to `/api/chat` (server authoritative). | MVP |
| W-13 | Accept / reject / accept-all / reject-all handlers update diff `status` from the response (`conversation_history` or changed statuses), not by local guess. Remove the current local history splicing in those handlers. | MVP |
| W-14 | Turns are not appended when the stream ends with `rate_limit` / `credit_limit` / `service_unavailable`; remove the optimistic pair in that case (backend doesn't store it either). | MVP |
| W-15 | Version select: render the returned `boundary` turn instead of clearing history. | MVP |
| W-16 | New Session / new upload: history cleared (unchanged). | MVP |

---

## 3. IndexedDB Mirror — `lib/versionCache.ts` (ADR-0014)

| # | Requirement | Priority |
|---|-------------|----------|
| W-20 | `CachedWorkspace` gains `conversationHistory: ChatTurn[]`. Saved in the same `saveWorkspace` effect as versions / JSON. | MVP |
| W-21 | Cap mirrored history to the last 200 turns (matches backend `chat_history_max_stored_turns`). | MVP |
| W-22 | Restore flow (backend restart → new session) passes `conversation_history` to `api.restoreVersions`. Older cache entries without the field restore with empty history (no DB_VERSION bump needed; field optional). | MVP |
| W-23 | `clearWorkspace` also clears history (already clears whole record). | MVP |

---

## 4. UI — `components/ChatPanel.tsx` / `DiffViewer.tsx`

| # | Requirement | Priority |
|---|-------------|----------|
| W-30 | Each diff in an assistant bubble shows a status badge: Pending (amber), Accepted (green), Rejected (grey, strikethrough), Failed (red, tooltip = `failure_reason`). Icons from lucide-react (ADR-0010). | MVP |
| W-31 | Accept / Reject buttons shown only for `pending` diffs; hidden for terminal statuses. | MVP |
| W-32 | Failed diffs rendered (collapsed "N changes couldn't be applied") so the user sees what the model tried. | MVP |
| W-33 | `boundary` turns render as a divider: "Switched to version X — earlier messages are not used as context". | MVP |
| W-34 | "Clear chat" button in the ChatPanel header. Calls `DELETE /api/sessions/{id}/chat`. On `409` (pending diffs), show a sonner toast (ADR-0009) with "Accept all" / "Reject all" actions, then retry. | MVP |
| W-35 | Context hint under the input when history is non-empty: "Using last N messages as context" (N = min(turns since boundary, 10)). | MVP |
| W-36 | Thread scrolls to bottom on hydration and on new turns (existing behaviour preserved). | MVP |

---

## 5. Data Flow

### 5.1 Page reload, backend alive

```
loadWorkspace() → sessionId → GET /api/sessions/{id} → conversationHistory = response.conversation_history
```

### 5.2 Page reload, backend restarted

```
GET session → 404 → POST /api/sessions → POST …/versions/restore {versions, working_json, baseline_json, conversation_history from IndexedDB}
→ render restored thread
```

### 5.3 Partial accept then follow-up

```
User accepts d1, rejects d2, leaves d3 → badges update from responses
User: "do the same for the rest" → POST /api/chat {session_id, message}  (no history in body)
Server replays statuses → new diffs exclude d1/d3 targets and d2's rejected change
```

---

## 6. Excluded from MVP

- Migrating chat state to Vercel AI SDK `useChat` / assistant-ui (separate UI-refactor ADR)
- Editing / regenerating past messages, branching
- Showing tool-call activity (Phase 2 backend tools)
- Server-side chat persistence UI for logged-in users (workspaces document chat, Phase 2)
- Search within chat history

---

*End of requirements. Feature branch: `chat-history`. Implementation files: `src/context/SessionContext.tsx`, `src/lib/api.ts`, `src/lib/versionCache.ts`, `src/components/ChatPanel.tsx`, `src/components/DiffViewer.tsx`.*
