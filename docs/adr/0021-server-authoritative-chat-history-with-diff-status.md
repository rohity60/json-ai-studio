# 0021-server-authoritative-chat-history-with-diff-status

**Date**: 2026-10-10
**Status**: Accepted

## Context

Chat turns were stateless: `GatewayService.invoke()` always sent `[system, user]`. A user who accepted "set retryCount to 3 for payments" and then asked "do it for all such services" got a failure — the model never saw turn 1. `conversation_history` only held assistant diffs (as an accept/reject lookup ledger), accept/reject outcomes were stored in flat id lists nobody read, and `accept_all` / `reject_all` erased them.

Options considered:

- **Memory frameworks** — LangChain (`RunnableWithMessageHistory`, `trim_messages`, `PostgresChatMessageHistory`), LlamaIndex (`ChatMemoryBuffer`), Mem0 / Zep / Letta.
- **Provider-native threads** — OpenAI Responses `previous_response_id` / Conversations API.
- **Client-held history** — browser sends the thread on every `/api/chat`.
- **Server-held history replayed via LiteLLM `messages`** — LiteLLM already in use (ADR-0002).
- **LLM tools** (function calling) to query diff history on demand.

## Decision

**The session's `conversation_history` is server-authoritative and replayed to the LLM through LiteLLM's native multi-turn `messages`, with a per-diff `status`. No memory framework, no new dependency.**

- Every chat turn stores a user turn and an assistant turn (explanation + diffs). Diffs carry `status`: `pending` (previewed) → `accepted` | `rejected`; `failed` for proposals that did not resolve. Accept/reject endpoints mutate the status in place.
- `services/chat_history_service.py` builds the replay: turns after the last `boundary` turn, last `CHAT_HISTORY_MAX_TURNS` pairs, assistant turns serialised in the model's own output contract (`{"diffs":[{path,operation,old_value,new_value,status}], "explanation"}`; `old_value` kept (compacted) because it carries the change's condition — prod eval 2026-10-10: without it a vague 'change for all players' follow-up overwrote whole arrays). Budget via `litellm.token_counter`; `fit_to_context()` drops oldest pairs against `litellm.get_model_info()` max input. History is always sacrificed before the system prompt.
- System prompt adds HISTORY RULES (only when history is present): resolve paths against the CURRENT WORKING JSON; never re-propose accepted/pending; don't repeat rejected unless asked; generalise "do it for all" from accepted/pending.
- `/api/chat` never accepts client history (prevents forged assistant turns). The browser mirrors the thread to IndexedDB (ADR-0014) and sends it only to `POST .../versions/restore` after a backend restart.
- Version select keeps the thread but appends a `boundary` turn and marks pending diffs rejected. New upload clears it. `DELETE /api/sessions/{id}/chat` clears it (409 while diffs are pending).

**Tools are deferred.** Inline status covers the bounded window cheaply on every provider; read-only tools (`get_diff_history`, `get_json_at_path`, `find_paths`) are a Phase 2 option for turns beyond the budget and skeleton-only large JSON, gated by a `supports_tools` deployment flag.

## Consequences

- Follow-ups work with no extra LLM round trips; prompt tokens grow by at most `CHAT_HISTORY_MAX_TOKENS` (default 8 000) per turn, billed through the existing cost path.
- Accept/reject of an already-resolved diff now returns 409.
- `ChatRequest.conversation_history` removed from the contract (was dead).
- History lives in the in-memory session store; logged-in DB persistence (`chat_messages`, ADR-0018 documents) is Phase 2.
- Frameworks rejected: they wrap a gateway we own (custom SSE, credits, deployment registry) for ~2 functions of value. Provider threads rejected: break round-robin across deployments.

## References

- PRD: `docs/prd/chat-history.prd`
- Requirements: `apps/api/ai/feature/chat-history/requirements.md`, `apps/web/ai/feature/chat-history/requirements.md`
- ADR-0002 (LiteLLM), ADR-0004 (SSE), ADR-0005 (prompt), ADR-0013 (store), ADR-0014 (IndexedDB)
