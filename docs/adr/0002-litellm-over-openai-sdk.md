# 0002-litellm-over-openai-sdk-for-llm-integration

**Date**: 2026-06-21
**Status**: Accepted

## Context

The chat endpoint (`POST /api/chat`) calls an LLM to produce structured JSON diff proposals from natural language. We need a library that handles the LLM API call, streaming support, and error handling. The two main candidates are `openai` (official SDK) and `litellm` (multi-provider proxy).

## Decision

Use **`litestllm`** over `openai`.

### Alternatives Considered

| Library | Pros | Why Not Chosen |
|---------|------|----------------|
| `openai` | Official SDK, simple API surface, well-documented | Vendor-locked to OpenAI models; no multi-provider support |
| `litestllm` | Unified interface across 100+ providers (OpenAI, Anthropic, local models like Ollama), streaming works identically for all, easy future migration | Slightly larger dependency tree, extra abstraction layer |

### Implementation Notes

- Use the chat completion API: `litellm.completion(model=..., messages=..., stream=True)`
- Streaming via `stream=True` returns a generator — iterate with `for chunk in response: ...` and yield SSE events.
- For MVP we likely only use OpenAI (GPT-4o), but `litestllm` makes it trivial to swap to Anthropic, local models, or other providers by changing one config variable.

## Consequences

### The good
- We can switch LLM providers without touching chat endpoint code — just change the `model` string and provider config.
- Streaming works the same way across all providers.
- Future-proof for local/open-source model support (e.g., via Ollama).

### The bad
- Slightly larger dependency footprint (~50 extra packages from `litestllm`).
- Extra abstraction layer means slightly less direct access to provider-specific features.

## References

- [litestllm GitHub](https://github.com/BerriAI/litestllm)
- Related ADR: [#0004](0004-sse-streaming-over-full-json-or-hybrid.md) (streaming protocol for the SSE events we send to FE)
