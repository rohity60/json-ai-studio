# 0024-lookup-tools-for-large-json

**Date**: 2026-10-24
**Status**: Accepted

## Context

Documents over `LLM_MAX_INLINE_CHARS` reach the model as a skeleton. Prod logs showed edits on hidden elements being refused or guessed (gita.json, 701 records) and analysis requests that were impossible (Unreal UAssetAPI dump: targets deep in `Exports[].ScriptBytecode`, references by numeric index). The skeleton itself showed only each array's first element, so for heterogeneous arrays whole sections were invisible (`ScriptBytecode` never appeared when `Exports[0]` was a `ClassExport`). PRD: `docs/prd/json-tools.prd`.

## Decision

1. **Key-union skeleton.** Each array's sample element merges keys from ALL elements ("…keys in only some items" lists partial keys); arrays whose elements carry `$type` show one merged sample per type with counts; nested arrays are merged across parents ("across N arrays"). Uniform arrays render as before. Field stats show short `$type` names.
2. **Three read-only tools**, offered only in skeleton mode on deployments with `supports_tools` (`json_tools.py`):
   - `search(query, scope=values|keys|both, path_prefix, context_levels, limit)` — free text inside one value or key name.
   - `query(path_with_*, where, limit)` — field conditions using the bulk-edit grammar; covers several fields at once and reverse reference lookups (`StackNode == -2`). Added after live evals: the model put `"slokNumber: 23, sectionId: …"` into `search`, which matches single values only.
   - `read(path)` — exact value / reference hops.
3. **Tool loop in the gateway**: up to `CHAT_TOOL_MAX_ROUNDS` (4) rounds, then a forced final answer; tool instructions appended to the system prompt only when tools are passed; usage summed, credits charged once; each call emitted as an SSE `tool` event (UI shows "Searching…/Reading…"). Every request carries the system prompt (with outline) once — APIs are stateless, so a 3-round turn sends it in 3 requests.
4. **Streaming by default** for tool rounds (`tool_streaming`, default true): text deltas go out as `draft` SSE events (keep-alive, not parsed), tool-call fragments are reassembled with `litellm.stream_chunk_builder`; the final answer is emitted once as `thinking` so parsing is unchanged.
5. **Ollama tool rounds use `ollama_chat/`** (`tool_litellm_model` hook): LiteLLM's `ollama/` route dropped native tool calls on the long system prompt (0 calls vs a correct `search` via `ollama_chat/`, same model and prompt). The non-tool streaming path keeps `ollama/`.
6. **Per-round retry** (relaxes ADR-0007 inside this loop only): a 429 with a provider retry hint ≤ `CHAT_TOOL_RETRY_MAX_WAIT_S` (10 s), or a 5xx/connection error (2 s back-off), retries that round up to `CHAT_TOOL_RETRY_ATTEMPTS` (2) times. Nothing has been shown to the user as an answer yet, and re-running one round is cheaper than failing or re-running a multi-round turn.
7. **Clarifying questions and analysis answers** (answer format, not tools): optional `question: {text, options[≤4]}` rendered as buttons (click sends the option); analysis requests may end with no diffs and a longer explanation citing paths.

## Consequences

- Live (Ollama gemma4:12b, Google gemma-4-26b): tools called and parsed in streaming and standard modes; `query` resolves the two-field gita case in one call (`/records/141`) on Google in both modes.
- **Google free tier: 16,000 input tokens per minute** for this model; a skeleton prompt is ~4k tokens per round, so multi-round turns approach or exceed the cap; ~⅓ of calls returned 500s on 2026-10-23. The per-round retry helps; a paid key (or a deployment without per-minute token caps) is needed for reliable multi-round tool turns in prod.
- Each tool round is a billed call — latency and cost grow with rounds (capped at 4).
- Deployments without `supports_tools` keep the pre-tools behaviour.

## References

- `docs/prd/json-tools.prd`; ADR-0021 (history), ADR-0022 (bulk edits), ADR-0023 (format hints), ADR-0007 (fail-fast)
- Tests: `tests/test_json_tools.py` (stubbed), `tests/test_json_tools_live.py` (`LIVE_LLM=1`; `LIVE_DEPLOYMENT`, `LIVE_TOOL_STREAMING`, `LIVE_CALL_SPACING_S`)
