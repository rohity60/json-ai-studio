# 0003-deepdiff-over-native-diff-for-backend-engine

**Date**: 2026-06-21
**Status**: Accepted

## Context

The backend needs to generate structured diffs between "before" and "after" versions of a session's JSON. These diffs feed two consumers: (1) the frontend diff viewer for rendering color-coded changes, and (2) the `DiffEntry` model stored per chat turn in the session. We need a library that handles nested dicts, lists, and scalars correctly while producing a clean output format.

## Decision

Use **`deepdiff`** on the backend and **`deep-diff`** (JS equivalent) on the frontend.

### Alternatives Considered

| Library | Pros | Why Not Chosen |
|---------|------|----------------|
| `json-repair / json-diff-py` | Simpler API, less code | Less mature ecosystem, limited support for nested structures |
| Build our own | Zero dependencies, full control | Slow to build, error-prone for edge cases (nested arrays, type coercion) |
| `deepdiff` (Python) | Mature, handles dicts/lists/scalars well, returns typed change objects | Slightly more complex output format to flatten into `DiffEntry` shape |

## Implementation Notes

- Backend: `from deepdiff import DeepDiff` → produces `{ 'changed': { '/path/to/key': { 'from_value': ..., 'to_value': ... } }, ... }`
- Flatten this output into our `DiffEntry` model: `{ path: str, operation: 'add'|'modify'|'delete', old_value: Any, new_value: Any }`.
- Frontend: same algorithm (`deep-diff` JS) used for client-side diff computation between versions.

## Consequences

### The good
- Deepdiff is one of the most widely-used Python diff libraries — well-tested against edge cases (circular refs, nested structures).
- Same conceptual model on both sides (Python ↔ JS) makes it easier to reason about diffs consistently.
- Produces structured output that maps cleanly to our `DiffEntry` model.

### The bad
- Output from deepdiff is a Python dict with path strings like `/a/b/c` — needs flattening into flat `DiffEntry` list.
- Extra dependency (~30KB on disk) for the MVP.

## References

- [deepdiff PyPI](https://pypi.org/project/deepdiff/)
- Related ADR: [#0005](0005-few-shot-prompt-strategy-over-instruction-only.md) (LLM uses deepdiff output to produce diff proposals)
