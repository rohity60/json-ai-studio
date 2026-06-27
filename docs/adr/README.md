# Architecture Decision Records (ADRs)

This directory contains all architectural decisions for **JSON AI Studio**.

## How to Write an ADR

Use the following template. Every ADR answers:
- **Context**: What problem are we facing? What's the situation?
- **Decision**: What did we choose and why?
- **Status**: Proposed | Accepted | Implemented | Superseded
- **Consequences**: What changes? What are the trade-offs?

```markdown
## 0XXX-title-slug

**Date**: YYYY-MM-DD
**Status**: [Accepted|Implemented|Superseded|Rejected]

### Context
What is the issue that we're seeing that makes us make this decision?

### Decision
What is the change that we will make (e.g. add this dependency, use that pattern)?

### Consequences
- The good: what becomes easier or better?
- The bad: what becomes more complex or worse?
- Neutrals: nothing changes or other effects

### References
Links to relevant discussions, PRDs, prior ADRs.
```

## Decision Log

| # | Title | Status | Date |
|---|-------|--------|------|
| [0001](0001-record-tech-decisions-with-adrs.md) | Record tech decisions with ADRs (meta-decision) | Accepted | 2026-06-21 |
| [0002](0002-litellm-over-openai-sdk-for-llm-integration.md) | Use `litestllm` for LLM integration | Accepted | 2026-06-21 |
| [0003](0003-deepdiff-over-native-diff-for-backend-engine.md) | Use `deepdiff` as diff engine (backend + frontend) | Accepted | 2026-06-21 |
| [0004](0004-sse-streaming-over-full-json-or-hybrid-for-chat-responses.md) | SSE streaming over full JSON or hybrid for chat responses | Accepted | 2026-06-21 |
| [0005](0005-few-shot-prompt-strategy-over-instruction-only-for-llm-diff-generation.md) | Few-shot prompt strategy; JSON in message body for context | Accepted | 2026-06-21 |
| [0006](0006-global-session-store-over-explicit-session-lifecycle-for-in-memory-storage.md) | Single global `SessionStore` with auto-generated UUIDs | Accepted | 2026-06-21 |
| [0007](0007-fail-fast-error-handling-over-retry-pattern-for-llm-calls.md) | Fail-fast error handling (500 + retry hint) for LLM calls | Accepted | 2026-06-21 |
| [0008](0008-cashify-react-json-view-over-native-or-alternatives-for-tree-rendering.md) | Use `@cashify/react-json-view` for JSON tree rendering | Accepted | 2026-06-21 |
| [0009](0009-sonner-over-react-hot-toast-or-native-for-toasts.md) | Use `sonner` for toast notifications | Accepted | 2026-06-21 |
| [0010](0010-lucide-react-over-native-or-alternatives-for-icon-library.md) | Use `lucide-react` for icon library | Accepted | 2026-06-21 |
| [0011](0011-api-contracts-per-interface-with-pydantic-as-source-of-truth.md) | Per-interface contracts; Pydantic = wire format (Option A) | Accepted | 2026-06-21 |
| [0012](0012-openapi-yaml-as-machine-readable-contract-spec-at-project-root.md) | OpenAPI YAML monolith at `openapi/spec.yaml` as machine-readable contract | Accepted | 2026-06-21 |

## Adding a New ADR

When you encounter a new technical decision:
1. Number it the next integer in sequence (e.g., if last is `0010`, create `0011-title-slug.md`)
2. Fill in **Context**, **Decision**, **Status**, **Consequences**, and **References**
3. Add a row to this table above
4. Update the relevant `requirements.md` file with the feature requirement (the WHAT), keep the technical choice in the ADR (the HOW)
