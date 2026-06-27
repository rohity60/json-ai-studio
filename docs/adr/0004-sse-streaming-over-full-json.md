# 0004-sse-streaming-over-full-json-or-hybrid-for-chat-responses

**Date**: 2026-06-21
**Status**: Accepted

## Context

The chat endpoint (`POST /api/chat`) calls an LLM to produce JSON diff proposals. We need to decide how to return that response to the frontend: a single full JSON payload after all processing, streaming in chunks via SSE, or a hybrid approach.

## Decision

Use **Server-Sent Events (SSE)** over both full JSON and hybrid approaches.

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **Full JSON diff (non-streaming)** | Simplest possible contract — one request, one response. Easy to handle errors/retries. | User sees a spinner for 2-3s of silence. Complex multi-field changes feel slow. | Not chosen — lacks the "live" feel essential for a chat-based editor. |
| **SSE (Option B)** | Feels instant — user sees thinking text immediately. Better UX for a conversational product. Sets up the feeling of a live assistant. `litestllm` supports streaming via unified API — no extra work. | Frontend needs an SSE consumer + state machine for partial/failed streams. More complex error handling (what if stream cuts off mid-diff?). | Chosen — trade-offs are acceptable and worth the UX benefit. |
| **Hybrid (fast thinking + streamed diff)** | Best of both worlds: immediate feedback + granular updates. | Most complex implementation. Three-step response model adds significant frontend state machine complexity. | Not for MVP — defer until we have a polished base. |

## SSE Event Types (Backend → Frontend)

| Event | Payload | Purpose |
|-------|---------|---------|
| `thinking` | `{ "text": "..." }` | LLM reasoning / intermediate step shown to user |
| `diff` | `{ "entry": { ... } }` | Individual diff entry from LLM or deepdiff |
| `complete` | `{ "working_json": {...}, "explanation": "..." }` | Final state after all diffs applied |

## Implementation Notes

- Backend: use FastAPI's `StreamingResponse` with a generator that yields `f"data: {json.dumps(payload)}\n\n"` for each event.
- Frontend: use `fetch()` + `ReadableStream` (not `EventSource`) since we need POST body support. Parse SSE format manually or via a lightweight library.
- Event types (`thinking`, `diff`, `complete`) map directly to frontend UI phases: inline thinking text → accumulate diffs in a list → apply diffs to working JSON and update preview panel.

## Consequences

### The good
- User sees "thinking" text immediately, building confidence in what the AI is doing before showing diffs.
- Aligns with modern chat products (Cursor, GitHub Copilot) — users expect streaming in conversational UIs.
- `litestllm` supports streaming natively via `stream=True` — no extra work to wire up.

### The bad
- Frontend needs an SSE consumer with state machine for handling partial/failed streams.
- More complex error handling: what if stream cuts off mid-diff? How do we handle a failed event parse?
- Non-LLM errors (session not found, validation failure) return standard 500 responses — need to distinguish these from streaming events on the frontend.

### Neutrals
- SSE is a well-established pattern with broad browser support (all modern browsers except IE).
- The wire format (`data: ...\n\n`) is simple and human-readable for debugging.

## References

- [MDN: Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Serverside_events/Using_serverside_events)
- Related ADR: [#0002](0002-litellm-over-openai-sdk.md) (`litestllm` supports streaming natively for this approach)
