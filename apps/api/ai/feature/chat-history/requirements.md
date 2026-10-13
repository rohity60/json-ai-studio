# Backend Requirements — JSON AI Studio Chat History

Derived from PRD `docs/prd/chat-history.prd`. Only what the **server / API layer** must implement.

---

## 1. Data Model — Turns & Diff Status

| # | Requirement | Priority |
|---|-------------|----------|
| H-01 | `ChatTurn` (`models.py`, `openapi/spec.yaml`) gains: `id: str` (uuid hex), `created_at: datetime`, `kind: Literal["message", "boundary"] = "message"`. `content` holds the user text (user turn) or the final explanation (assistant turn). | MVP |
| H-02 | `DiffEntry` gains `status: Literal["pending", "accepted", "rejected", "failed"] = "pending"` and optional `failure_reason: str \| None`. | MVP |
| H-03 | Every chat turn appends **two** turns to `session["conversation_history"]`: the user turn, then the assistant turn — including turns with zero diffs (clarifications, refusals, errors). | MVP |
| H-04 | Applied diffs stored with `status="pending"`. Diffs skipped by `DiffUtils.apply_all_verbose` (the `failed` list) stored with `status="failed"` + `failure_reason`. Failed diffs get an id but no `diff` SSE event (unchanged). | MVP |
| H-05 | Turns are not stored when the stream ended on a quota event (`rate_limit` / `credit_limit` / `service_unavailable`) — the user message was never processed. | MVP |
| H-06 | Remove the flat `applied_diffs` / `rejected_diffs` session lists as source of truth; keep them in responses for backward compatibility, derived from turn statuses. | MVP |
| H-07 | `ChatRequest.conversation_history` stays out of `/api/chat`: the endpoint never accepts client-supplied history (server authoritative). Remove the dead field from `ChatRequest` in spec + models. | MVP |

### Turn shape (stored + wire)

```json
{"id": "a1…", "role": "assistant", "kind": "message", "created_at": "2026-10-10T12:00:00Z",
 "content": "Set retryCount to 3 for payments.",
 "diffs": [
   {"id": "d1…", "path": "/services/payments/retryCount", "operation": "modify",
    "old_value": 5, "new_value": 3, "status": "accepted"},
   {"id": "d2…", "path": "/services/x/retryCount", "operation": "modify",
    "old_value": 1, "new_value": 3, "status": "failed", "failure_reason": "path not found"}
 ]}
```

---

## 2. Status Lifecycle — `services/diff_service.py`

| # | Requirement | Priority |
|---|-------------|----------|
| S-01 | `accept_one` sets the matching diff's `status="accepted"` (only from `pending`; accepting non-pending → 409). | MVP |
| S-02 | `reject_one` sets `status="rejected"` (only from `pending`; else 409). | MVP |
| S-03 | `accept_all` sets every `pending` diff in history to `accepted` (no longer wipes outcome). | MVP |
| S-04 | `reject_all` sets every `pending` diff to `rejected`. | MVP |
| S-05 | All four responses include `conversation_history` (or the changed turn ids + statuses) so the client mirror stays in sync. | MVP |
| S-06 | `_find_diff_in_history` returns `(turn, diff)` so status can be mutated in place; followed by `store.save_session` (get → mutate → save discipline, ADR-0013). | MVP |
| S-07 | Status transitions are terminal: `accepted`, `rejected`, `failed` never change again. | MVP |

---

## 3. `ChatHistoryService` — `services/chat_history_service.py` (new)

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | `build_messages(session, new_message, system_prompt, model) -> list[dict]` returns `[system, *history, user]` in LiteLLM/OpenAI message format. | MVP |
| C-02 | History = turns after the last `boundary` turn, last `chat_history_max_turns` user/assistant **pairs**. A user turn is never sent without its assistant reply. | MVP |
| C-03 | Assistant turns serialised in the model's own output contract: `{"diffs": [{"path","operation","old_value","new_value","status"}...], "explanation": "<content>"}`. `old_value` kept (compacted) because it carries the change's condition — prod eval 2026-10-10: without it a vague 'change for all players' follow-up overwrote whole arrays; `failure_reason` included for `failed`. | MVP |
| C-04 | Compaction: `new_value` JSON-serialised and truncated to `chat_history_value_max_chars` (default 300) with `"…(truncated)"`; max `chat_history_max_diffs_per_turn` (default 20) diffs per turn + `"…and N more diffs (statuses: …)"` summary entry. | MVP |
| C-05 | Token budget: `litellm.token_counter(model=…, messages=…)` on history; drop oldest pairs until ≤ `chat_history_max_tokens` (default 8 000). | MVP |
| C-06 | Context guard: if `token_counter(system + history + user) + llm_max_tokens` exceeds `litellm.get_model_info(model)["max_input_tokens"]` (when known), drop more history; final fallback `litellm.utils.trim_messages(...)`. History is always sacrificed before the system prompt. | MVP |
| C-07 | Status is read **at request time** from the session, so an accept/reject done after a turn is reflected in the next turn's replay. | MVP |
| C-08 | `CHAT_HISTORY_ENABLED=false` → `build_messages` returns `[system, user]` (today's behaviour). | MVP |
| C-09 | Logging (ADR-0017): INFO `history turns_sent=%d turns_dropped=%d history_tokens=%d`; DEBUG full message list. | MVP |

### Settings (`settings.py`, pydantic Settings — no manual env parsing)

| Field | Default |
|-------|---------|
| `chat_history_enabled: bool` | `True` |
| `chat_history_max_turns: int` | `10` |
| `chat_history_max_tokens: int` | `8_000` |
| `chat_history_value_max_chars: int` | `300` |
| `chat_history_max_diffs_per_turn: int` | `20` |
| `chat_history_max_stored_turns: int` | `200` (oldest pruned from the session to bound memory / IndexedDB) |

---

## 4. Gateway & Prompt

| # | Requirement | Priority |
|---|-------------|----------|
| G-01 | `GatewayService.invoke()` accepts `messages: list[dict]` instead of `(system_prompt, message)`; `explain()` keeps building its own 2-message list. Credit check / cost / deployment selection unchanged. Cost naturally covers extra prompt tokens. | MVP |
| G-02 | `chat_service._stream_llm` calls `ChatHistoryService.build_messages` and passes the list to `invoke`. | MVP |
| P-01 | `prompting.py` adds a `HISTORY RULES` block, included only when history is non-empty (see PRD rules 1–5: resolve against CURRENT JSON; accepted/pending already applied, never re-propose; rejected = don't repeat unless asked; failed = re-derive paths; "do it for all" = generalise from latest accepted/pending, skip rejected-equivalents). | MVP |
| P-01a | Rule H5a: generalise at the SAME granularity — one leaf diff per location whose CURRENT value matches the earlier `old_value`; never replace whole arrays/objects or touch non-matching values unless asked. | MVP |
| P-02 | Add one few-shot example: turn 1 accepted diff on `/services/payments/retryCount`, turn 2 "do it for all such services" → diffs for every other service with `retryCount`, none for payments. | MVP |
| P-03 | Rule 10 (pasted JSON) unchanged; history assistant turns are trusted server data, user turns are untrusted as today. | MVP |

---

## 5. Endpoints & Contract (`openapi/spec.yaml` first)

| # | Requirement | Priority |
|---|-------------|----------|
| E-01 | `GET /api/sessions/{id}` returns full `conversation_history` with statuses (already in `SessionResponse`; now populated). | MVP |
| E-02 | New `DELETE /api/sessions/{id}/chat` — clears `conversation_history`. Returns `409` if any diff is still `pending` (its id would become un-acceptable); client must accept-all / reject-all first. `204` on success. | MVP |
| E-03 | `POST /api/sessions/{id}/versions/select` no longer wipes history: appends a `kind="boundary"` turn (`content: "Switched to version <label>"`). Pending diffs from the previous version are marked `rejected`. Turns before the boundary are not replayed to the LLM (C-02) but stay visible. | MVP |
| E-04 | `RestoreVersionsRequest` gains optional `conversation_history: list[ChatTurn]`. Server validates shape, caps to `chat_history_max_stored_turns`, and stores it. This is the **only** path where client history enters the server. | MVP |
| E-05 | New session / `/api/json/upload` start with empty history (unchanged). | MVP |
| E-06 | SSE: `complete` payload gains `user_turn_id` and `assistant_turn_id`; `diff` event entries carry `status: "pending"`. Event names/order unchanged (ADR-0004). | MVP |

---

## 6. Data Flow

### 6.1 Follow-up turn

```
1. POST /api/chat {session_id, message}
2. chat_service: session = get_session(); system = build_system_prompt(working_json, has_history)
3. messages = ChatHistoryService.build_messages(session, message, system, model)
4. GatewayService.invoke(messages) → stream thinking → parse → apply_all_verbose
5. emit diff(status=pending)…, complete{working_json, explanation, turn ids}
6. append user turn + assistant turn (applied=pending, skipped=failed) → save_session
```

### 6.2 Partial accept

```
POST …/diffs/d1/accept → d1.status=accepted (baseline updated)
POST …/diffs/d2/reject → d2.status=rejected (working reverted)
(d3 untouched → pending)
Next chat turn replays: d1 accepted, d2 rejected, d3 pending
```

### 6.3 Backend restart

```
Client GET session → 404 → create session → POST …/versions/restore {versions, working_json, baseline_json, conversation_history}
```

---

## 7. Phase 2 — Read-only LLM Tools

| # | Requirement | Priority |
|---|-------------|----------|
| T-01 | Deployment config flag `supports_tools: bool` (mirrors `supports_thinking`); enabled only when also `litellm.supports_function_calling(model)` is true or unknown-but-flagged. | P2 |
| T-02 | `get_diff_history(path_prefix?: str, status?: str, limit?: int ≤ 50)` — searches **all** stored turns, including those dropped from the prompt budget. | P2 |
| T-03 | `get_json_at_path(pointer: str)` — exact value from working JSON (truncated to 4 000 chars); used when the system prompt carried only the skeleton. | P2 |
| T-04 | `find_paths(key?: str, value_equals?: Any, limit ≤ 200)` — JSON Pointers matching a key name / value. | P2 |
| T-05 | Tool loop inside `GatewayService.invoke`: max 3 tool rounds; tool results never streamed as `thinking`; each round billed through the existing cost path. Tools are read-only — diffs are still only produced in the final JSON answer. | P2 |
| T-06 | Postgres `chat_messages` table (Alembic) keyed by workspace `json_document_id` for logged-in users (ADR-0018). | P2 |

---

## 8. Excluded from MVP

- Tool / function calling (Phase 2 above)
- DB persistence of chat for logged-in users
- LLM summarisation of dropped turns
- Explain output in chat context
- Editing / regenerating a past message, branching threads
- Cross-session or cross-document memory

---

*End of requirements. Feature branch: `chat-history`. Implementation files: `services/chat_history_service.py` (new), `services/chat_service.py`, `services/diff_service.py`, `services/version_service.py`, `gateway.py`, `prompting.py`, `models.py`, `settings.py`, `controllers/sessions.py`, `openapi/spec.yaml`. Tests: `tests/test_chat_history.py` (stubbed LLM, always run), `tests/test_chat_history_live.py` (real model, `LIVE_LLM=1`, prod follow-up cases).*
