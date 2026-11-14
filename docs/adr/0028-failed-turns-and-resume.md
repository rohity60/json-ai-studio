# 0028-failed-turns-and-resume

**Date**: 2026-11-14
**Status**: Proposed

## Context

On large documents a chat turn is a multi-round lookup loop (ADR-0024) that can run for minutes under a deployment budget (ADR-0025). Until now a turn was stored only when it completed: a provider error, a call timeout or a closed connection in round 3 threw away rounds 1–2, their waits and their tokens, and the next turn had no idea anything had been attempted, so the model started over or repeated itself. Amends ADR-0021 (chat history).

## Decision

1. **Every turn that reached the model is stored.** The assistant turn gains `status` (`complete` | `failed` | `interrupted`, default `complete`), `error_code` (`provider_error`, `timeout`, `rate_limit`, `internal_error`, `interrupted`) and `read_paths` (paths already read, at most 20). A failure is stored when the model was called at least once; quota stops (scope `user`), `input_too_large` and a capacity stop before the first call stay unstored as before. A client disconnect (cancellation or generator close) stores the turn as `interrupted` synchronously while the stream unwinds.

2. **Server-only trace.** `services/turn_trace.py` keeps, per failed turn, `{json_hash, focus_path, plan, calls, error_code, round_reached, messages_snapshot, tool_calls: [{id, round, name, args, result_chars, paths, hashes}]}` in `session["turn_traces"]` — beside the turns, not on them, so it never reaches the wire (`public_session` strips it) and is never sent to the model verbatim. The gateway fills it: model calls counted before each call, the conversation snapshot (without the system prompt) and the paths each lookup depended on with a hash of their values after every finished round, `error_code` in its failure handlers. Only the latest turn keeps a trace; it is dropped when a later turn completes, the chat is cleared or a new document is loaded. In memory only: a backend restart loses it (accepted).

3. **Resume** — `POST /api/sessions/{id}/turns/{turnId}/resume` (SSE, same events as `/api/chat`). Only the session's last turn, if it is a failed/interrupted assistant turn with a trace, can be resumed: unknown turn or trace gone → 404, otherwise not resumable or already running → 409. The planner runs again for the current document; the tool loop starts after `round_reached` with a fresh system prompt plus the snapshot, so finished rounds are not re-run. On success the same assistant turn becomes `complete` in place (no new user turn); a second resume → 409. A new failure keeps the turn failed and resumable.

4. **Stale rule.** If the document hash changed since the turn started, each lookup whose paths now hash differently keeps its tool-call/result pairing but its result is replaced with a short "stale, look it up again" note; the rest is reused. Search/query/outline depend on the subtree they looked in (the whole document for an unscoped search). When no lookup survives, resume simply re-sends the original message.

5. **SSE `error`** `{error, code, turn_id, user_turn_id, read_paths, resumable}` is sent before the terminal event (`service_unavailable` / `rate_limit` / `complete`), so older clients keep their popup and new ones show the failed turn inline with **Continue** instead.

6. **History replay.** A failed/interrupted turn replays as `{"diffs": [], "explanation": "(previous attempt failed: <code>; read: /a, /b)"}` — never the tool results. A new `/api/chat` message after a failure simply proceeds. Older user messages longer than `CHAT_HISTORY_USER_MAX_CHARS` (1500) replay as head 1000 + `…(N chars omitted)` + tail 300; the latest replayed one stays whole.

7. **Web.** Failed turns render muted with an "Attempt failed" badge and the read paths; Continue appears on the latest failed turn only, disabled while a chat or review stream runs, and disappears on 404/409. The IndexedDB mirror stores the new fields as-is; after a backend restart the restored turn shows failed, and Continue answers 404 and hides.

## Consequences

- One failed turn's snapshot (tool results included) stays in memory until the next turn completes; bounded to one trace per session.
- A DB-backed `SessionStore` must persist turn `status`/`error_code`/`read_paths`; persisting traces is optional (resume degrades to 404).
- Retries remain server policy (ADR-0025); the client never resumes on its own.
- Not done here: provider safety blocks as their own `error.code` (`safety_block`, PRD B B-20..B-26) and progress steps in the trace (B-57).
