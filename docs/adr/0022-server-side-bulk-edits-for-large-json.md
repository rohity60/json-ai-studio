# 0022-server-side-bulk-edits-for-large-json

**Date**: 2026-10-11
**Status**: Accepted

## Context

Documents larger than `LLM_MAX_INLINE_CHARS` (120k) reach the model as a structural skeleton: one sample element per array plus "…+N more items" (ADR-0005). Production case (gita.json, 701 records, 491k chars): "change sectionId for slok 1" worked, "slok 1 to 10" worked only because the model *guessed* the hidden values, and "all records" / "first 100" / "first 20" were refused — the model cannot see the elements. Even with the full document visible, hundreds of per-element diffs exceed `LLM_MAX_TOKENS` and truncate.

Chat history (ADR-0021) was not the blocker: the model understood the intent but had no way to express it.

## Decision

**The model may emit `bulk` ops — a JSON Pointer pattern with `*` wildcards plus a `where` filter — which the server expands against the FULL working JSON into ordinary diffs** (`bulk_edits.py`).

```json
{"diffs": [], "bulk": [{"path": "/records/*/sectionId", "where": {"$index": {"lt": 100}},
  "operation": "modify", "new_value": "abc"}], "explanation": "..."}
```

- `where` evaluates against the node matched by the last `*`: field names / relative pointers, `$index`, `$value`; operators eq, ne, in, nin, gt(e), lt(e), contains (case-insensitive), exists. Plain value = equality.
- Operations: modify, add (only where missing), delete. No-op modifies are dropped. Matches capped by `BULK_MAX_MATCHES` (5000) per op.
- Expanded diffs carry real `old_value`s and flow through the unchanged apply / accept / reject / status / history path. The op itself is stored on the assistant turn (`ChatTurn.bulk`) and replayed on follow-ups.
- The explanation always reports `Bulk edit matched N location(s)` (or "matched nothing"), so a wrong filter is visible before accepting.
- Skeleton prompt: instead of "refuse large rewrites", instructs bulk ops, and adds **ARRAY FIELD STATS** per array (distinct counts, numeric ranges, top category values, "unique per element") so the model can see that e.g. `slokNumber` (1..78 across 701 items) restarts per chapter and is not a position.

## Consequences

- Large-document bulk edits work with a tiny model output; the server — not the model — decides which elements match.
- Filter choice is still the model's: a small local model (gemma4:12b) sometimes picks a plausible-but-wrong field. The match count in the explanation + per-diff reject are the safety net.
- Output contract gained an optional `bulk` key; `diffs` stays required. No API endpoint changes.
- Related fix found while testing locally: the Ollama provider now sends `think` explicitly and `num_ctx` (`OLLAMA_NUM_CTX`, default 32k). Previously reasoning "none" sent nothing, Gemma 4 thought until the 120s timeout and returned no content.

## References

- ADR-0005 (prompt / skeleton), ADR-0021 (chat history), ADR-0016 (deployments)
- `apps/api/src/json_ai_studio/bulk_edits.py`, `prompting.py` (`build_array_stats`), `providers/ollama.py`
- Tests: `apps/api/tests/test_bulk_edits.py`; live: `tests/test_chat_history_live.py -k gita` (`LIVE_LLM=1`, pinned to local Ollama by default)
