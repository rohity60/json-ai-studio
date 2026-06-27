# 0007-fail-fast-over-retry-pattern-for-llm-call-error-handling

**Date**: 2026-06-21
**Status**: Accepted

## Context

LLM calls can fail in multiple ways: rate limits, timeouts, malformed responses, provider outages. We need a strategy for error handling on the backend that returns meaningful feedback to the frontend while keeping code simple for MVP.

## Decision

Use **Fail-Fast with 500 + Retry Hint** over retry-then-fail pattern.

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **Fail-fast (one attempt)** | Simplest implementation. No retry boilerplate code. Explicit about failures — user sees the error immediately. Response latency is predictable (just one LLM call timeout). | User has to re-send the message if it fails once. No automatic recovery from transient issues like rate limits or brief network blips. | Chosen — MVP simplicity over retry logic that adds code without significant UX benefit for a chat-based editor. |
| **Retry-then-fail (1-2 retries for transient errors)** | Better UX — handles rate limits gracefully, recovers from brief outages automatically. Higher success rate on first try. | Slightly more code to implement (retry logic, jitter, backoff). Latency spikes on retry are invisible to the streaming user. More complex to reason about in SSE context. | Not chosen — retry overhead not justified for MVP's single-user chat pattern. |

### Error Response Format

When an LLM call fails:

```json
{
   "error": "LLM call failed: timeout after 5000ms",
   "hint": "Please try again.",
   "status": 500
}
```

Non-LLM errors (validation failures, missing session) use appropriate HTTP codes: `400`, `404`, `422`.

## Implementation Notes

- Set a 5-second timeout on the LLM call. If it exceeds this, raise an exception immediately.
- Catch all exceptions at the FastAPI middleware / endpoint level and return the structured error response above.
- Frontend displays the `error` message in the chat stream with a "Try again" action button.

## Consequences

### The good
- Extremely simple backend code — just one LLM call, no retry loops or jitter logic.
- Explicit about failures — user knows exactly what went wrong (not a silent timeout).
- Predictable response latency: if it fails, it fails fast (~5s max).

### The bad
- User has to manually re-send the message on first failure — rate limits and transient outages block progress.
- No automatic recovery — a brief LLM provider hiccup blocks the user entirely.
- Higher perceived failure rate compared to retry-based approaches (which users may find more "resilient").

### Neutrals
- For MVP's single-user chat pattern, failure rates are expected to be low enough that manual retries are acceptable friction.
- If error rates increase in later phases, this decision is easily reversible — add a simple `for _ in range(3): try: ... except: continue` loop.

## References

- Related ADR: [#0002](0002-litellm-over-openai-sdk.md) (`litestllm` handles the LLM API call and timeout)
- Related ADR: [#0005](0005-few-shot-prompt-strategy-over-instruction-only.md) (how we handle malformed LLM output with validation)
