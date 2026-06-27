# 0005-few-shot-prompt-strategy-over-instruction-only-for-llm-diff-generation

**Date**: 2026-06-21
**Status**: Accepted

## Context

The chat endpoint calls an LLM to convert natural language messages into structured JSON diff proposals. The prompt needs to produce output that maps cleanly to our `DiffEntry` model: `{ path, operation ('add'|'modify'|'delete'), old_value, new_value }`. We need to decide how to structure the prompt and where to place the working JSON context.

## Decision 1a — Prompt Format

Use **Few-Shot Examples + Instruction** over instruction-only.

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **Instruction-only** | Simpler prompt, fewer tokens in context, faster inference per call. | LLM may inconsistently format diff output. More validation/correction needed on the backend side to fix malformed diffs. | Not chosen — structured JSON output is critical for our frontend diff viewer. Inconsistent formatting breaks rendering. |
| **Few-shot + Instruction** | Higher accuracy on structured output format. Consistent shape of `DiffEntry` objects across turns. Easier to validate output schema on the backend. | More tokens in context, prompt grows with each example (adds ~300-500 tokens per call). | Chosen — the reliability gain for structured JSON output is worth the token cost. |

### Example Prompt Structure

```
You are a JSON configuration assistant. Given the current working JSON and a user message, return structured diff proposals.

Working JSON:
{ "services": { "api": { "timeout": 30 } } }

User Message: "Increase timeout to 60 for all services."

Examples of output format:
[
  { "path": "/services/api/timeout", "operation": "modify", "old_value": 30, "new_value": 60 }
]

Now process the user's message and return diffs in this exact format.
```

## Decision 1b — JSON Context Placement

Place the **working JSON in the message body** (NOT in the system prompt).

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **JSON string in message body** | LLM sees both context + request in one prompt. Easy to update working JSON per turn — just replace the variable. | Context window pressure grows with large JSON files (up to 20 MB). | Chosen — same JSON appears every turn, and putting it in system prompt would be redundant when we can swap it per call. |
| **JSON as system prompt** | Clean separation of concerns. LLM sees "context" vs "request" distinctly. | Same JSON is sent in every turn → wastes tokens repeating identical context. Harder to update without regenerating the full system prompt. | Not chosen — redundant content per turn wastes tokens and increases cost/latency. |

## Implementation Notes

- Construct the prompt dynamically per call: inject working JSON as a variable into the message body, append few-shot examples from a static template file.
- The LLM's output should be valid JSON array of `DiffEntry` objects — wrap in try/except for parsing safety.
- If the LLM returns malformed JSON, return a 500 error with retry hint (see ADR-0007).

## Consequences

### The good
- Few-shot examples dramatically improve structured output accuracy — consistent `DiffEntry` shape across turns means frontend rendering is reliable.
- Message-body placement of working JSON lets us swap context per call without regenerating system prompts, saving tokens on every turn.
- Easier to add more few-shot examples as we discover new edge cases (bulk updates, conditional modifications).

### The bad
- Prompt grows with each example — ~300-500 extra tokens per call adds up in cost for high-traffic use.
- Few-shot examples are static — they won't adapt to new patterns discovered later without code changes.

## References

- Related ADR: [#0002](0002-litellm-over-openai-sdk.md) (`litestllm` handles the LLM API call)
- Related ADR: [#0007](0007-fail-fast-error-handling-over-retry-pattern.md) (how we handle malformed LLM output)
